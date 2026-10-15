"""Verify installed Mac runtime, independent model storage and offline PDF export."""
import argparse,json,os
from pathlib import Path
import subprocess,textwrap


def main():
    p=argparse.ArgumentParser();p.add_argument('profile',choices=['standard','precision']);p.add_argument('--app',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);a=p.parse_args()
    a.evidence.mkdir(parents=True,exist_ok=True)
    resources=a.app/'Contents/Resources'
    code=r'''
from pathlib import Path
import hashlib,json,os,shutil,time,urllib.request
from paperbridge.paths import ROOT,CODE_ROOT
from paperbridge.gguf_inference import block_external_network
block_external_network()
def forbidden_download(*a,**k):raise AssertionError('Offline export attempted an external download')
urllib.request.urlopen=forbidden_download
profile=os.environ['PB_TEST_PROFILE'];evidence=Path(os.environ['PB_TEST_EVIDENCE']);bundle=Path(os.environ['PB_TEST_APP'])
from paperbridge.app import add_document,get_job,save_job,status
from paperbridge.layout_runtime import CACHE
if not (CACHE/'ready.json').is_file():shutil.copytree(bundle/'Contents/Resources/LayoutAssets',CACHE,dirs_exist_ok=True)
model=ROOT/'models'/('qwen3-14b' if profile=='precision' else 'qwen3-4b')
assert not model.is_symlink() and not model.resolve().is_relative_to(bundle.resolve())
metadata=json.loads((model/'installation.json').read_text())
assert metadata['repo']==('Qwen/Qwen3-14B-MLX-4bit' if profile=='precision' else 'Qwen/Qwen3-4B-MLX-4bit')
import pymupdf as fitz
source=CODE_ROOT/'examples/sci-layout-sample.pdf'
if not source.is_file():source=Path(os.environ['PB_TEST_SAMPLE'])
created=add_document(source.read_bytes(),'Mac-offline-'+profile+'.pdf')
job=get_job(created['id']);job['settings'].update(engine='full',profile=profile,domain='general',glossary='',polish=False,pages='',auto_cleanup=False)
save_job(job)
from paperbridge.full_worker import run
started=time.perf_counter();run(job['id'])
folder=ROOT/'data/jobs'/job['id'];result=json.loads((folder/'worker-state.json').read_text())
assert result['status']=='complete',result.get('message')
with fitz.open(source) as before,fitz.open(folder/'translated.pdf') as after:
 assert len(before)==len(after)
 assert all(tuple(x.rect)==tuple(y.rect) for x,y in zip(before,after))
 assert any('\u3400'<=c<='\u9fff' for page in after for c in page.get_text())
assert result['export_report']['structural_checks_passed']
assert (folder/'bilingual.pdf').is_file()
report={'status':'complete','profile':profile,'runtime':str(bundle/'Contents/Resources/Python/bin/python3.12'),'model_outside_application':True,'model_is_independent_directory':True,'model_revision':metadata['revision'],'downloads_forbidden':True,'actual_pdf_export':True,'elapsed_seconds':round(time.perf_counter()-started,1),'job_id':job['id'],'export_report':result['export_report']}
(evidence/('MACOS-OFFLINE-'+profile.upper()+'-REPORT.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
shutil.copy2(folder/'translated.pdf',evidence/('Mac-'+profile+'-中文.pdf'))
shutil.copy2(folder/'bilingual.pdf',evidence/('Mac-'+profile+'-双语.pdf'))
print(json.dumps({'status':'complete','profile':profile,'seconds':report['elapsed_seconds']},ensure_ascii=True),flush=True)
'''
    script=a.evidence/f'offline-{a.profile}.py';script.write_text('def main():\n'+textwrap.indent(code.strip(),'    ')+"\n\nif __name__=='__main__':\n    main()\n")
    env={**os.environ,'PYTHONPATH':str((resources/'Engine').resolve()),'PAPERBRIDGE_HOME':str(a.data.resolve()),'PAPERBRIDGE_APP_VERSION':'1.8','PYTHONDONTWRITEBYTECODE':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','PB_TEST_PROFILE':a.profile,'PB_TEST_EVIDENCE':str(a.evidence.resolve()),'PB_TEST_APP':str(a.app.resolve()),'PB_TEST_SAMPLE':str(Path('examples/sci-layout-sample.pdf').resolve())}
    with (a.evidence/f'offline-{a.profile}.log').open('w') as log:
        result=subprocess.run([str((resources/'Python/bin/python3.12').resolve()),'-X','utf8',str(script.resolve())],cwd=resources/'Engine',env=env,stdout=log,stderr=log,timeout=1800)
    if result.returncode:
        print((a.evidence/f'offline-{a.profile}.log').read_text()[-6000:]);raise SystemExit(result.returncode)
    print((a.evidence/f'MACOS-OFFLINE-{a.profile.upper()}-REPORT.json').read_text()[:700])


if __name__=='__main__':main()
