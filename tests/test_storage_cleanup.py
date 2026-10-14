import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paperbridge.storage_cleanup import cleanup_after_task
import paperbridge.app as module


def make_job(tmp_path):
    folder = tmp_path / ('a' * 32); folder.mkdir()
    job = {'id': folder.name, 'status': 'complete', 'has_output': True,
           'settings': {}, 'segments': [{'id':'s1','translation':'人工校订','status':'edited'}],
           'document_term_overrides':'flux ratio = 通量比',
           'export_report':{'structural_checks_passed':True}}
    originals = {}
    for name in ['original.pdf','translated.pdf','bilingual.pdf','job.json','quality.json','paragraph-cache.json','document-terminology.json']:
        content = json.dumps(job).encode() if name == 'job.json' else name.encode()
        (folder / name).write_bytes(content); originals[name] = content
    work = folder / 'layout-work'; work.mkdir(); (work / 'temporary.pdf').write_bytes(b'temporary')
    (folder / 'translated.new.pdf').write_bytes(b'unfinished')
    archive = folder / 'history' / '20261003-123456-abcdef12'; archive.mkdir(parents=True)
    (archive / 'job.json').write_text(json.dumps(job)); (archive / 'translated.pdf').write_bytes(b'old PDF')
    job['translation_baseline'] = str(archive.relative_to(folder))
    return folder, job, originals, archive


def test_success_removes_only_rebuildable_files_and_generated_versions(tmp_path):
    folder,job,originals,archive = make_job(tmp_path)
    report = cleanup_after_task(folder,job,succeeded=True)
    assert report['status']=='complete' and report['old_versions_removed']==1 and report['removed_bytes']>0
    assert not (folder/'layout-work').exists() and not archive.exists()
    assert 'translation_baseline' not in job
    assert job['segments'][0]['translation']=='人工校订'
    assert all((folder/name).read_bytes()==data for name,data in originals.items())


@pytest.mark.parametrize('state',['failed','cancelled','running','complete'])
def test_failure_or_failed_structure_keeps_rollback_and_resume_records(tmp_path,state):
    folder,job,originals,archive=make_job(tmp_path);job['status']=state
    if state=='complete':job['export_report']['structural_checks_passed']=False
    cleanup_after_task(folder,job,succeeded=state=='complete')
    assert archive.exists() and not (folder/'layout-work').exists()
    assert all((folder/name).read_bytes()==data for name,data in originals.items())


def test_cleanup_disabled_and_unknown_or_foreign_archives_are_retained(tmp_path):
    folder,job,_,archive=make_job(tmp_path)
    job['settings']['auto_cleanup']=False
    assert cleanup_after_task(folder,job,succeeded=True)['status']=='disabled'
    assert archive.exists() and (folder/'layout-work').exists()
    job['settings']['auto_cleanup']=True
    (archive/'user-notes.txt').write_text('Keep my notes')
    foreign=folder/'history'/'20261003-123457-abcdef12';foreign.mkdir()
    (foreign/'job.json').write_text(json.dumps({'id':'b'*32}))
    (foreign/'translated.pdf').write_bytes(b'another paper')
    cleanup_after_task(folder,job,succeeded=True)
    assert archive.exists() and foreign.exists()


def test_missing_current_pdf_or_diagnostic_does_not_remove_last_good_version(tmp_path):
    folder,job,_,archive=make_job(tmp_path);(folder/'bilingual.pdf').unlink()
    cleanup_after_task(folder,job,succeeded=True);assert archive.exists()
    (folder/'bilingual.pdf').write_bytes(b'dual');job['export_report']['layout_test']=True
    cleanup_after_task(folder,job,succeeded=True);assert archive.exists()


def test_symlink_cannot_remove_outside_data(tmp_path):
    folder,job,_,archive=make_job(tmp_path)
    outside=tmp_path/'outside';outside.mkdir();(outside/'keep.pdf').write_bytes(b'keep')
    (folder/'layout-work'/'link').symlink_to(outside,target_is_directory=True)
    (archive/'translated.pdf').unlink();(archive/'translated.pdf').symlink_to(outside/'keep.pdf')
    cleanup_after_task(folder,job,succeeded=True)
    assert (outside/'keep.pdf').read_bytes()==b'keep' and archive.exists()


def test_cleanup_error_does_not_turn_a_valid_export_into_failure(tmp_path,monkeypatch):
    import paperbridge.storage_cleanup as cleanup
    folder,job,originals,_=make_job(tmp_path)
    monkeypatch.setattr(cleanup.shutil,'rmtree',lambda *args,**kwargs: (_ for _ in ()).throw(PermissionError()))
    report=cleanup_after_task(folder,job,succeeded=True)
    assert report['status']=='partial' and report['errors'] and job['status']=='complete'
    assert all((folder/name).read_bytes()==data for name,data in originals.items())


def test_missing_check_and_malformed_archive_are_not_pruned(tmp_path):
    folder,job,_,archive=make_job(tmp_path)
    job['export_report']={}
    cleanup_after_task(folder,job,succeeded=True);assert archive.exists()
    job['export_report']['structural_checks_passed']=True
    (archive/'job.json').write_text('[]')
    cleanup_after_task(folder,job,succeeded=True);assert archive.exists()


def test_history_read_failure_is_reported_without_losing_final_pdf(tmp_path,monkeypatch):
    folder,job,originals,archive=make_job(tmp_path)
    original_iterdir=Path.iterdir
    def read_directory(path):
        if path.name=='history':raise PermissionError()
        return original_iterdir(path)
    monkeypatch.setattr(Path,'iterdir',read_directory)
    report=cleanup_after_task(folder,job,succeeded=True)
    assert report['status']=='partial' and archive.exists() and job['status']=='complete'
    assert all((folder/name).read_bytes()==data for name,data in originals.items())


def test_storage_switch_does_not_reset_existing_translations(tmp_path,monkeypatch):
    class HoldingExecutor:
        def submit(self, *args, **kwargs):
            pass
    folder,job,_,_=make_job(tmp_path)
    job.update(name='paper.pdf',progress=100,page_count=1,settings={'domain':'general','glossary':'','polish':True,'pages':'','engine':'full','profile':'standard'})
    job['segments']=[{'id':'s1','page':1,'source':'A scientific result.','translation':'已有中文。','status':'review','exported':True}]
    monkeypatch.setattr(module,'DATA',tmp_path);monkeypatch.setattr(module,'jobs',{job['id']:job})
    monkeypatch.setattr(module,'executor',HoldingExecutor());monkeypatch.setattr(module,'layout_ready',lambda:True);monkeypatch.setattr(module.translator,'installed',lambda:True)
    with TestClient(module.app) as client:
        response=client.post(f"/api/documents/{job['id']}/translate",json={**job['settings'],'auto_cleanup':False})
        assert response.status_code==200
        assert job['segments'][0]['translation']=='已有中文。' and job['segments'][0]['status']=='review'
        assert job['settings']['auto_cleanup'] is False


def test_storage_preference_saves_without_translation_or_immediate_deletion(tmp_path,monkeypatch):
    folder,job,originals,archive=make_job(tmp_path)
    monkeypatch.setattr(module,'DATA',tmp_path);monkeypatch.setattr(module,'jobs',{job['id']:job})
    with TestClient(module.app) as client:
        response=client.put(f"/api/documents/{job['id']}/storage-settings",json={'auto_cleanup':False})
    assert response.status_code==200 and job['settings']['auto_cleanup'] is False
    assert json.loads((folder/'job.json').read_text())['settings']['auto_cleanup'] is False
    assert job['segments'][0]['translation']=='人工校订' and archive.exists() and (folder/'layout-work').exists()
    assert all((folder/name).read_bytes()==data for name,data in originals.items() if name!='job.json')


@pytest.mark.parametrize('state',['running','queued','exporting'])
def test_storage_preference_cannot_change_during_processing(tmp_path,monkeypatch,state):
    folder,job,_,archive=make_job(tmp_path);job['status']=state
    monkeypatch.setattr(module,'DATA',tmp_path);monkeypatch.setattr(module,'jobs',{job['id']:job})
    with TestClient(module.app) as client:
        response=client.put(f"/api/documents/{job['id']}/storage-settings",json={'auto_cleanup':False})
    assert response.status_code==409 and 'auto_cleanup' not in job['settings'] and archive.exists()


def test_abnormal_worker_exit_releases_and_cleans_work_but_keeps_previous_pdf(tmp_path,monkeypatch):
    folder,job,originals,archive=make_job(tmp_path)
    class Worker:
        stdout=[]
        def wait(self):return 7
    monkeypatch.setattr(module,'DATA',tmp_path);monkeypatch.setattr(module,'jobs',{job['id']:job})
    monkeypatch.setattr(module.subprocess,'Popen',lambda *args,**kwargs:Worker())
    module.run_full_translation(job['id'])
    assert job['status']=='failed' and job['cleanup_report']['model_memory_released'] is True
    assert not (folder/'layout-work').exists() and archive.exists()
    assert all((folder/name).read_bytes()==data for name,data in originals.items() if name!='job.json')
