import json

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient

import paperbridge.app as module
from paperbridge.pdf_compaction import compact_pdf, verify_identical
from tests.test_storage_cleanup import make_job


def scientific_pdf(path):
    with fitz.open() as doc:
        for i in range(2):
            page = doc.new_page(width=400, height=500)
            page.insert_text((30, 60), "中文论文：引力透镜与光变曲线", fontname="china-s", fontsize=14)
            page.insert_text((30, 90), "F = 1.23, sigma = 0.4", fontsize=10)
            page.draw_rect(fitz.Rect(30, 120, 250, 180))
            page.insert_image(fitz.Rect(30, 200, 80, 250), pixmap=fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 3, 3), False))
            page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(30, 50, 220, 65), "uri": "https://example.org/paper"})
        doc.save(path)


def test_font_subset_preserves_chinese_math_images_links_and_every_page(tmp_path):
    path = tmp_path / "paper.pdf"
    scientific_pdf(path)
    before = path.read_bytes()
    report = compact_pdf(path)
    assert report["status"] == "optimized" and report["after_bytes"] < report["before_bytes"]
    assert report["checked_pages"] == 2
    with fitz.open(stream=before, filetype="pdf") as old, fitz.open(path) as new:
        verify_identical(old, new)
        assert "引力透镜" in new[0].get_text()


def test_mismatching_export_falls_back_to_untouched_pdf(tmp_path, monkeypatch):
    path = tmp_path / "paper.pdf"
    scientific_pdf(path)
    before = path.read_bytes()
    subset = fitz.Document.subset_fonts
    def changed(doc):
        subset(doc)
        doc[1].draw_rect(fitz.Rect(30, 300, 200, 350), fill=(1, 0, 0))
    monkeypatch.setattr(fitz.Document, "subset_fonts", changed)
    report = compact_pdf(path)
    assert report["status"] == "skipped" and path.read_bytes() == before
    assert not path.with_suffix(".compact.pdf").exists()


def test_font_subset_skips_annotation_text(tmp_path):
    path = tmp_path / "paper.pdf"
    scientific_pdf(path)
    with fitz.open(path) as doc:
        doc[0].add_text_annot((30, 300), "用户批注")
        doc.saveIncr()
    before = path.read_bytes()
    assert compact_pdf(path)["status"] == "skipped"
    assert path.read_bytes() == before


def test_manual_cleanup_ignores_auto_preference_and_retains_results_and_edits(tmp_path, monkeypatch):
    folder, job, originals, archive = make_job(tmp_path)
    job['settings']['auto_cleanup'] = False
    monkeypatch.setattr(module, 'DATA', tmp_path)
    monkeypatch.setattr(module, 'jobs', {job['id']: job})
    monkeypatch.setattr(module, 'active_operations', set())
    monkeypatch.setattr(module, 'release_idle_memory', lambda _: None)
    with TestClient(module.app) as client:
        result = client.post('/api/cleanup')
    assert result.status_code == 200 and result.json()['removed_bytes'] > 0
    assert not archive.exists() and not (folder/'layout-work').exists()
    assert job['settings']['auto_cleanup'] is False
    assert job['segments'][0]['translation'] == '人工校订'
    assert all((folder/name).read_bytes() == value for name,value in originals.items() if name != 'job.json')


@pytest.mark.parametrize('state', ['queued', 'running', 'exporting', 'child_exiting', 'installing'])
def test_manual_cleanup_rejects_active_work_before_releasing_model(tmp_path, monkeypatch, state):
    folder, job, originals, archive = make_job(tmp_path)
    if state in {'queued', 'running', 'exporting'}:
        job['status'] = state
    monkeypatch.setattr(module, 'DATA', tmp_path)
    monkeypatch.setattr(module, 'jobs', {job['id']: job})
    monkeypatch.setattr(module, 'active_operations', {job['id']} if state == 'child_exiting' else set())
    monkeypatch.setattr(module, 'install_state', {'status': 'running' if state == 'installing' else 'idle'})
    monkeypatch.setattr(module, 'release_idle_memory', lambda _: pytest.fail('busy model must remain loaded'))
    with TestClient(module.app) as client:
        result = client.post('/api/cleanup')
    assert result.status_code == 409 and archive.exists() and (folder/'layout-work').exists()
    assert all((folder/name).read_bytes() == value for name,value in originals.items())


def test_whole_task_time_survives_worker_state_and_reexport(tmp_path, monkeypatch):
    folder, job, _, _ = make_job(tmp_path)
    job['settings']['auto_cleanup'] = False
    job['timing'] = {'kind': 'translation'}
    class Worker:
        def __init__(self):
            (folder/'worker-state.json').write_text(json.dumps({**job, 'status':'complete', 'timing':{'ignored':True}}))
            self.stdout = ['{"event":"state"}']
        def wait(self): return 0
    monkeypatch.setattr(module, 'DATA', tmp_path)
    monkeypatch.setattr(module, 'jobs', {job['id']: job})
    monkeypatch.setattr(module, 'active_operations', set())
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *a,**kw: Worker())
    times = iter([100, 172.4, 200, 211.2])
    monkeypatch.setattr(module.time, 'monotonic', lambda: next(times))
    module.run_full_translation(job['id'])
    assert job['last_translation_timing']['elapsed_seconds'] == 72.4
    original_timing = job['last_translation_timing'].copy()
    module.run_full_translation(job['id'], replay=True)
    assert job['last_translation_timing'] == original_timing
    assert job['timing']['kind'] == 'export' and job['timing']['elapsed_seconds'] == 11.2
    assert not module.active_operations


def test_memory_counts_workers_and_tolerates_process_exiting(monkeypatch):
    from types import SimpleNamespace
    import paperbridge.resources as resources
    class Process:
        def memory_info(self): return SimpleNamespace(rss=123)
        def children(self, recursive): return [SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=456))]
    monkeypatch.setattr(resources.psutil, 'Process', Process)
    usage = resources.memory_usage()
    assert usage['rss_bytes'] == 579 and usage['worker_bytes'] == 456
    monkeypatch.setattr(Process, 'children', lambda *a,**k: (_ for _ in ()).throw(PermissionError()))
    assert resources.memory_usage()['available'] is False


def test_idle_memory_cleanup_unloads_model_and_preview_cache(monkeypatch):
    from types import SimpleNamespace
    import paperbridge.resources as resources
    calls = []
    monkeypatch.setattr(fitz.TOOLS, 'store_shrink', lambda percent: calls.append(('preview', percent)))
    monkeypatch.setattr(resources.gc, 'collect', lambda: calls.append(('gc', True)))
    resources.release_idle_memory(SimpleNamespace(unload=lambda: calls.append(('model', True))))
    assert calls == [('model', True), ('preview', 100), ('gc', True)]
