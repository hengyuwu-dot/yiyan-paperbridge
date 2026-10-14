import fcntl
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import paperbridge.app as module
from paperbridge.storage import cleanup_targets, storage_inventory, safe_path
from tests.test_storage_cleanup import make_job


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / 'software'
    data = root / 'data' / 'jobs'
    data.mkdir(parents=True)
    folder, job, originals, archive = make_job(data)
    files = {
        'models/qwen3-14b/model.safetensors': b'keep verified model',
        'models/qwen3-14b/model.safetensors.download': b'incomplete download',
        'models/qwen3-14b/model.safetensors.chunks/0': b'download chunk',
        'models/qwen3-14b/user-notes.txt.download': b'keep unknown',
        '.cache/pip/http/download': b'installation cache',
        '.cache/babeldoc/fonts/font.ttf': b'keep offline layout resource',
        '.venv/lib/runtime.py': b'keep working environment',
        '论文PDF/中文.pdf': b'keep saved result',
        'tmp/layout-install.log': b'old installation log',
    }
    for name, content in files.items():
        p = root/name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(content)
    (folder/'full-worker.log').write_text('old runtime log')
    failures = folder/'translation-failures'; failures.mkdir()
    (failures/('b'*20+'.json')).write_text('old diagnostic')
    (failures/'user-notes.txt').write_text('keep custom notes')
    monkeypatch.setattr(module, 'ROOT', root)
    monkeypatch.setattr(module, 'DATA', data)
    monkeypatch.setattr(module, 'jobs', {job['id']: job})
    monkeypatch.setattr(module, 'active_operations', set())
    monkeypatch.setattr(module, 'install_state', {'status':'idle'})
    return root, data, folder, job, originals, archive


def selection(**updates):
    return {**dict.fromkeys(['memory','temporary','backups','downloads','logs'],False), **updates}


def test_disk_inventory_and_preview_are_read_only_and_match_allocated_space(setup):
    root, data, folder, job, originals, archive = setup
    before = {p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result = storage_inventory(root,data,refresh=True)
    expected = sum(p.stat().st_blocks * 512 for p in root.rglob('*') if p.is_file())
    assert result['software_bytes'] == expected == sum(row['bytes'] for row in result['groups'])
    assert result['disk']['total_bytes'] > result['disk']['free_bytes'] > 0
    rows = {row['id']:row for row in result['choices']}
    assert rows['memory']['bytes'] == 0
    assert rows['temporary']['files'] == 2 and rows['backups']['files'] == 2
    assert rows['downloads']['files'] == 3 and rows['logs']['files'] == 3
    assert before == {p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert not result['partial']


def test_portable_runtime_is_counted_but_cannot_be_cleaned(setup, tmp_path, monkeypatch):
    root, data, *_ = setup
    contents = tmp_path / '译研.app' / 'Contents'
    resources = contents / 'Resources'
    runtime = resources / 'Python' / 'lib' / 'runtime.bin'
    runtime.parent.mkdir(parents=True)
    runtime.write_bytes(b'keep bundled runtime')
    monkeypatch.setenv('PAPERBRIDGE_BUNDLE_RESOURCES', str(resources))
    before = storage_inventory(root, data, refresh=True)
    rows = {row['id']: row for row in before['groups']}
    assert rows['runtime']['logical_bytes'] == len(b'keep working environment') + len(b'keep bundled runtime')
    with TestClient(module.app) as client:
        result = client.post('/api/cleanup', json=selection(temporary=True, backups=True, downloads=True, logs=True))
    assert result.status_code == 200
    assert runtime.read_bytes() == b'keep bundled runtime'


@pytest.mark.parametrize('category',['temporary','backups','downloads','logs','memory'])
def test_each_cleanup_choice_removes_only_selected_contents(setup,monkeypatch,category):
    root,data,folder,job,originals,archive = setup
    unloaded = []
    monkeypatch.setattr(module,'release_idle_memory',lambda _:unloaded.append(True))
    with TestClient(module.app) as client:
        result = client.post('/api/cleanup',json=selection(**{category:True}))
    assert result.status_code == 200
    assert result.json()['selected'] == [category]
    assert bool(unloaded) == (category == 'memory')
    assert (folder/'layout-work').exists() == (category != 'temporary')
    assert archive.exists() == (category != 'backups')
    assert (root/'.cache/pip').exists() == (category != 'downloads')
    assert (root/'models/qwen3-14b/model.safetensors.download').exists() == (category != 'downloads')
    assert (folder/'full-worker.log').exists() == (category != 'logs')
    assert (folder/'translation-failures/user-notes.txt').read_text() == 'keep custom notes'
    for name,content in originals.items():
        if name != 'job.json' or category in {'memory','downloads','logs'}:
            assert (folder/name).read_bytes() == content
    assert (root/'models/qwen3-14b/model.safetensors').read_bytes() == b'keep verified model'
    assert (root/'models/qwen3-14b/user-notes.txt.download').read_bytes() == b'keep unknown'
    assert (root/'.cache/babeldoc/fonts/font.ttf').read_bytes() == b'keep offline layout resource'
    assert (root/'论文PDF/中文.pdf').read_bytes() == b'keep saved result'
    assert job['segments'][0]['translation'] == '人工校订'


def test_preview_and_deletion_share_history_eligibility(setup):
    root,data,folder,job,_,archive = setup
    job['export_report']['structural_checks_passed'] = False
    import json
    (folder/'job.json').write_text(json.dumps(job))
    rows = {r['id']:r for r in storage_inventory(root,data,refresh=True)['choices']}
    assert rows['backups']['bytes'] == 0
    with TestClient(module.app) as client:
        assert client.post('/api/cleanup',json=selection(backups=True)).status_code == 200
    assert archive.exists()


def test_symlinked_parent_cannot_escape_cleanup_or_inflate_inventory(setup,tmp_path):
    root,data,folder,job,_,archive = setup
    outside = tmp_path/'outside'; outside.mkdir(); (outside/'keep.pdf').write_bytes(b'keep source')
    import shutil
    shutil.rmtree(root/'.cache/pip')
    (root/'.cache/pip').symlink_to(outside,target_is_directory=True)
    (folder/'full-worker.log').unlink(); (folder/'full-worker.log').symlink_to(outside/'keep.pdf')
    targets,_ = cleanup_targets(root,data)
    assert root/'.cache/pip' not in targets['downloads'] and folder/'full-worker.log' not in targets['logs']
    assert not safe_path(root,root/'.cache/pip/keep.pdf')
    with TestClient(module.app) as client:
        assert client.post('/api/cleanup',json=selection(downloads=True,logs=True)).status_code == 200
    assert (outside/'keep.pdf').read_bytes() == b'keep source'
    assert (root/'.cache/pip').is_symlink()


def test_external_downloader_lock_rejects_cleanup_before_any_mutation(setup,monkeypatch):
    root,data,folder,job,originals,archive = setup
    monkeypatch.setattr(module,'release_idle_memory',lambda _:pytest.fail('locked cleanup must not unload'))
    with (root/'models/.installation.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with TestClient(module.app) as client:
            result = client.post('/api/cleanup',json=selection(memory=True,temporary=True,downloads=True))
    assert result.status_code == 409 and (folder/'layout-work').exists()
    assert (root/'models/qwen3-14b/model.safetensors.download').exists()
    assert all((folder/name).read_bytes() == value for name,value in originals.items())


def test_empty_or_unknown_cleanup_options_are_rejected(setup,monkeypatch):
    monkeypatch.setattr(module,'release_idle_memory',lambda _:pytest.fail('invalid options must not unload'))
    with TestClient(module.app) as client:
        assert client.post('/api/cleanup',json=selection()).status_code == 400
        assert client.post('/api/cleanup',json={'originals':True}).status_code == 422


def test_large_directory_scan_is_cached_but_cleanup_estimate_refreshes(setup,monkeypatch):
    root,data,folder,job,_,archive = setup
    import paperbridge.storage as storage
    before = storage_inventory(root,data,refresh=True)
    original = storage.file_stats
    def scan(path,errors):
        if Path(path) == root:pytest.fail('poll must reuse the cached full scan')
        yield from original(path,errors)
    monkeypatch.setattr(storage,'file_stats',scan)
    (folder/'layout-work/more.bin').write_bytes(b'new temporary file')
    after = storage_inventory(root,data)
    assert after['software_bytes'] == before['software_bytes']
    assert next(r for r in after['choices'] if r['id']=='temporary')['files'] == 3


def test_hard_links_are_not_double_counted_or_promised_as_reclaimable(setup):
    root,data,folder,job,_,archive = setup
    source = root/'models/qwen3-14b/model.safetensors'
    before = storage_inventory(root,data,refresh=True)['software_bytes']
    os.link(source,root/'tmp/linked-model')
    assert storage_inventory(root,data,refresh=True)['software_bytes'] == before
