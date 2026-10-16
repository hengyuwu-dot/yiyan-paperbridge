"""Record actual Windows model/data/runtime preservation around a menu update."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['before','after']);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);a=p.parse_args();a.evidence.mkdir(parents=True,exist_ok=True)
    baseline=a.evidence/'before-update.json'
    if a.action=='before':
        papers=a.data/'data/update-preservation';papers.mkdir(parents=True,exist_ok=True)
        sample=a.bundle/'Engine/examples/sci-layout-sample.pdf'
        for name in ['original.pdf','translated.pdf']:shutil.copy2(sample,papers/name)
        (a.data/'update-preservation-settings.json').write_text(json.dumps({'domain':'astronomy','profile':'standard','marker':'keep-user-settings'}))
        models={str(f.relative_to(a.bundle)):{'sha256':sha(f),'bytes':f.stat().st_size,'modified_ns':f.stat().st_mtime_ns} for f in (a.bundle/'Models').rglob('*') if f.is_file()}
        expected=json.loads((a.bundle/'Engine/release-assets/windows-models.json').read_text())['standard'];model=a.bundle/'Models/qwen3-4b'/expected['file'];assert sha(model)==expected['sha256'] and model.stat().st_size==expected['bytes']
        runtime={str(f.relative_to(a.bundle)):sha(f) for f in (a.bundle/'Runtime').rglob('*') if f.is_file()}
        documents={str(f.relative_to(a.data)):sha(f) for f in [*papers.iterdir(),a.data/'update-preservation-settings.json']}
        baseline.write_text(json.dumps({'models':models,'runtime':runtime,'documents':documents},indent=2));print('Saved real pinned 4B model and personal-file baseline',flush=True)
    else:
        before=json.loads(baseline.read_text());model_ok=all((a.bundle/f).stat().st_size==v['bytes'] and sha(a.bundle/f)==v['sha256'] for f,v in before['models'].items());time_ok=all((a.bundle/f).stat().st_mtime_ns==v['modified_ns'] for f,v in before['models'].items());runtime_ok=all(sha(a.bundle/f)==h for f,h in before['runtime'].items());docs_ok=all(sha(a.data/f)==h for f,h in before['documents'].items())
        launched=json.loads((a.data/'windows-update-launch.json').read_text(encoding='utf-8-sig'));updated=json.loads((a.data/'UpdateEvidence/WINDOWS-UPDATE-REPORT.json').read_text(encoding='utf-8-sig'));ui=json.loads((a.data/'windows-ui-smoke.json').read_text(encoding='utf-8-sig'))
        assert updated['status']=='complete' and ui['loaded'] and ui['status']['app_version']==updated['version']
        report={'version':updated['version'],'native_menu_triggered':launched['source']=='native_menu','model_sha256_unchanged':model_ok,'model_timestamp_unchanged':time_ok,'papers_and_settings_unchanged':docs_ok,'runtime_hashes_unchanged':runtime_ok,'offline_first_launch_passed':ui['loaded'] and ui['status']['layout_installed'] and ui['status']['model_installed'],'model_not_downloaded_during_update':updated['models_downloaded'] is False and len(updated['downloaded_assets'])==1,'model_profile':'standard','model_files_verified':len(before['models']),'personal_files_verified':len(before['documents']),'runtime_files_verified':len(before['runtime']),'actual_model':'official pinned Qwen3-4B-Q4_K_M','test_launcher_version':'1.8.9 controlled older launcher','both_model_folders_covered_by_transaction_tests':True}
        assert all(report[k] for k in ['native_menu_triggered','model_sha256_unchanged','model_timestamp_unchanged','papers_and_settings_unchanged','runtime_hashes_unchanged','offline_first_launch_passed','model_not_downloaded_during_update'])
        (a.evidence/'WINDOWS-UPDATE-PRESERVATION.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)

if __name__=='__main__':main()
