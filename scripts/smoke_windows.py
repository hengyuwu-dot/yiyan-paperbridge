"""Exercise the distributed Python engine with a real offline 4B PDF run."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import textwrap

ROOT = Path(__file__).resolve().parents[1]


def main():
    bundle = ROOT / "dist/windows/Yiyan"
    python = bundle / "Runtime/Python/python.exe"
    data = ROOT / ".cache/windows-smoke"
    data.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, PAPERBRIDGE_HOME=str(data),
                       PAPERBRIDGE_LLAMA_DIR=str(bundle / "Runtime/llama"),
                       PAPERBRIDGE_CPU_ONLY="1", PYTHONUTF8="1")
    # All sample prose is synthetic, generated specifically for this check.
    code = r'''
from pathlib import Path
import json, shutil, time
from paperbridge.paths import CODE_ROOT, ROOT
shutil.copytree(CODE_ROOT / '.cache/babeldoc', ROOT / '.cache/babeldoc', dirs_exist_ok=True)
from scripts.download_model import install
install(print)
import pymupdf as fitz
from paperbridge.app import add_document, get_job, save_job
doc=fitz.open(); page=doc.new_page(width=595,height=842)
page.insert_text((50,60),'Scientific reading example',fontsize=15)
page.insert_textbox(fitz.Rect(50,95,540,220),'The supernova light curve provides information about the progenitor. We estimate a posterior distribution using Bayesian inference.',fontsize=12)
page.draw_rect(fitz.Rect(50,280,240,370),color=(0.2,0.5,0.3))
page.insert_text((65,315),'Synthetic figure',fontsize=10)
created=add_document(doc.tobytes(),'Windows-local-engine-test.pdf'); doc.close()
job=get_job(created['id']); job['settings'].update(engine='full',profile='standard',domain='astronomy',glossary='progenitor = 前身星',polish=False,pages='',auto_cleanup=False)
save_job(job)
print('SMOKE_JOB='+job['id'],flush=True)
from paperbridge.full_worker import run
started=time.perf_counter(); run(job['id'])
folder=ROOT/'data/jobs'/job['id']; result=json.loads((folder/'worker-state.json').read_text(encoding='utf-8'))
assert result['status']=='complete',result['message']
with fitz.open(folder/'translated.pdf') as pdf:
    text=''.join(page.get_text() for page in pdf)
    assert len(pdf)==1
    assert any('\u3400' <= c <= '\u9fff' for c in text),text
assert (folder/'bilingual.pdf').is_file()
assert result['export_report']['structural_checks_passed']
report={'platform':'Windows x64','engine':'llama.cpp CPU','model':'Qwen3-4B-Q4_K_M','elapsed_seconds':round(time.perf_counter()-started,1),'status':result['status'],'has_chinese_pdf':True,'structure_passed':True,'export_report':result['export_report']}
(ROOT/'WINDOWS-SMOKE-REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(folder/'translated.pdf',ROOT/'Windows-smoke-translated.pdf')
shutil.copy2(folder/'bilingual.pdf',ROOT/'Windows-smoke-bilingual.pdf')
'''
    script = data / "run.py"
    script.write_text("def main():\n" + textwrap.indent(code.strip(), "    ") + "\n\nif __name__ == '__main__':\n    main()\n", encoding="utf-8")
    with (data / "smoke.log").open("w", encoding="utf-8") as log:
        result = subprocess.run([str(python), "-X", "utf8", str(script)], env=environment,
                                cwd=bundle / "Engine", stdout=log, stderr=log, timeout=1800)
    if result.returncode:
        print((data / "smoke.log").read_text(encoding="utf-8")[-12000:])
        for inference_log in (data / 'tmp').glob('inference-*.log'):
            print(inference_log.read_text(encoding='utf-8', errors='replace')[-8000:])
        raise SystemExit(result.returncode)
    print((data / "WINDOWS-SMOKE-REPORT.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
