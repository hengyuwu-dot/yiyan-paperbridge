import json
from pathlib import Path
from fastapi.testclient import TestClient
import paperbridge.app as module

class HoldingExecutor:
    def __init__(self): self.calls = []
    def submit(self, *args, **kwargs): self.calls.append((args, kwargs))

def test_settings_changes_keep_manual_edits_and_prior_export(tmp_path, monkeypatch):
    doc = {'id':'a'*32,'name':'test.pdf','status':'complete','progress':100,'page_count':4,
           'settings':{'domain':'general','glossary':'','polish':True,'pages':'','engine':'full','profile':'standard'},
           'has_output':True,'segments':[
               {'id':'s1','page':2,'source':'A scientific result.','translation':'科研结果。','status':'review','exported':True},
               {'id':'s2','page':3,'source':'Another result.','translation':'另一个结果。','status':'review','exported':True}]}
    translated = [s for s in doc['segments'] if s['translation']]
    translated[0]['status'] = 'edited'
    chosen = translated[0]['translation']
    folder = tmp_path / doc['id']; folder.mkdir()
    (folder / 'translated.pdf').write_bytes(b'prior-result')
    (folder / 'job.json').write_text(json.dumps(doc))
    monkeypatch.setattr(module,'DATA',tmp_path)
    monkeypatch.setattr(module,'jobs',{doc['id']:doc})
    executor = HoldingExecutor(); monkeypatch.setattr(module,'executor',executor)
    monkeypatch.setattr(module,'layout_ready',lambda:True)
    monkeypatch.setattr(module.translator,'installed',lambda:True)
    with TestClient(module.app) as client:
        settings = {**doc['settings'],'pages':'2-3'}
        result = client.post(f"/api/documents/{doc['id']}/translate",json=settings)
        assert result.status_code == 200
        assert translated[0]['status'] == 'edited' and translated[0]['translation'] == chosen
        assert (folder / doc['translation_baseline'] / 'translated.pdf').read_bytes() == b'prior-result'
        assert len(executor.calls) == 1
        assert client.post(f"/api/documents/{doc['id']}/translate",json=settings).status_code == 409
        assert client.post(f"/api/documents/{doc['id']}/cancel").status_code == 200
        assert doc['status'] == 'cancelled'
        monkeypatch.setattr(module,'run_full_translation',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('cancelled job must not load model')))
        module.run_translation(doc['id'],settings)
        assert doc['status'] == 'cancelled'
        response = client.post(f"/api/documents/{doc['id']}/translate",json={**settings,'pages':'3'})
        assert response.status_code == 409 and '校订' in response.json()['detail']
        assert translated[0]['translation'] == chosen


def test_high_resolution_preview_and_bounded_size(tmp_path, monkeypatch):
    import pymupdf as fitz
    from paperbridge.pdf_engine import render_page
    folder = tmp_path / ('b' * 32); folder.mkdir()
    path = folder / 'original.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page(width=400, height=600)
        page.insert_text((30,40),'Fine scientific text',fontsize=8)
        pdf.save(path)
    low = fitz.Pixmap(render_page(path,1,width=1100))
    high = fitz.Pixmap(render_page(path,1,width=2200))
    assert high.width == 2200 and high.height == 3300
    assert high.width > low.width and high.height > low.height
    monkeypatch.setattr(module,'DATA',tmp_path)
    monkeypatch.setattr(module,'jobs',{'b'*32:{'id':'b'*32}})
    with TestClient(module.app) as client:
        assert client.get(f"/api/documents/{'b'*32}/page/1?width=999999").status_code == 400
        assert client.get(f"/api/documents/{'b'*32}/page/1?width=2200").status_code == 200


def test_stale_cancelled_queue_entry_cannot_restart_a_resubmitted_job(tmp_path,monkeypatch):
    doc={'id':'c'*32,'name':'test.pdf','status':'ready','progress':0,'page_count':2,
         'settings':{},'has_output':False,'segments':[{'status':'pending','page':1,'translation':'','source':'Science.'}]}
    folder=tmp_path/doc['id'];folder.mkdir()
    monkeypatch.setattr(module,'DATA',tmp_path);monkeypatch.setattr(module,'jobs',{doc['id']:doc})
    executor=HoldingExecutor();monkeypatch.setattr(module,'executor',executor)
    monkeypatch.setattr(module,'layout_ready',lambda:True);monkeypatch.setattr(module.translator,'installed',lambda:True)
    with TestClient(module.app) as client:
        settings={'profile':'standard','engine':'full'}
        assert client.post(f"/api/documents/{doc['id']}/translate",json=settings).status_code==200
        client.post(f"/api/documents/{doc['id']}/cancel")
        assert client.post(f"/api/documents/{doc['id']}/translate",json=settings).status_code==200
        first=executor.calls[0][0];second=executor.calls[1][0]
        assert first[-1] != second[-1]
        calls=[];monkeypatch.setattr(module,'run_full_translation',lambda *a,**kw:calls.append((a,kw)))
        module.run_translation(*first[1:]);assert not calls
        module.run_translation(*second[1:]);assert len(calls)==1
