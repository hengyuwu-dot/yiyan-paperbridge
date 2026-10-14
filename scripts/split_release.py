"""Prepare verifiable release parts below GitHub's 2 GiB asset limit."""
import hashlib
import json
from pathlib import Path
import shutil
import stat
import re

PART_SIZE = 1800 * 1024 * 1024


def split_release(source, destination, part_size=PART_SIZE):
    source, destination = Path(source), Path(destination)
    if not re.fullmatch(r'[A-Za-z0-9._-]+', source.name) or part_size <= 0:
        raise ValueError('Use a plain ASCII release filename and a positive part size')
    destination.mkdir(parents=True, exist_ok=True)
    records, whole = [], hashlib.sha256()
    with source.open('rb') as stream:
        number = 1
        while True:
            first = stream.read(min(8 * 1024 * 1024, part_size))
            if not first:
                break
            target = destination / f'{source.name}.part{number:03d}'
            checksum, total = hashlib.sha256(), 0
            with target.open('wb') as output:
                chunk = first
                while chunk:
                    output.write(chunk); checksum.update(chunk); whole.update(chunk); total += len(chunk)
                    chunk = stream.read(min(8 * 1024 * 1024, part_size-total)) if total < part_size else b''
            records.append({'file': target.name, 'bytes': total, 'sha256': checksum.hexdigest()})
            number += 1
            print(f'Prepared {target.name}: {total/1e9:.2f} GB', flush=True)
    manifest = {'output': source.name, 'bytes': source.stat().st_size, 'sha256': whole.hexdigest(), 'parts': records}
    (destination / 'PARTS.json').write_text(json.dumps(manifest, indent=2))
    # macOS ships /usr/bin/osascript, shasum and Ruby-independent shell tools;
    # use a plain shell merger so downloading users need no Python installation.
    checks = '\n'.join(f"{row['sha256']}  {row['file']}" for row in records)
    (destination / 'PARTS-SHA256.txt').write_text(checks+'\n')
    names = ' '.join('"'+row['file']+'"' for row in records)
    merger = '''#!/bin/zsh
set -eu
cd "${0:A:h}"
echo "正在核对下载分卷；缺失或损坏时会停止。"
/usr/bin/shasum -a 256 -c PARTS-SHA256.txt
OUTPUT="__OUTPUT__"
if [[ -e "$OUTPUT" ]]; then
  echo "已有同名安装包，正在核对。"
  echo "__SHA__  $OUTPUT" | /usr/bin/shasum -a 256 -c -
else
  TEMP="$OUTPUT.merging"
  trap 'rm -f "$TEMP"' EXIT
  echo "正在合并安装包，请等待。"
  /bin/cat __PARTS__ > "$TEMP"
  echo "__SHA__  $TEMP" | /usr/bin/shasum -a 256 -c -
  /bin/mv -n "$TEMP" "$OUTPUT"
fi
echo "完整安装包校验通过。"
/usr/bin/open "$OUTPUT"
'''.replace('__OUTPUT__',source.name).replace('__SHA__',whole.hexdigest()).replace('__PARTS__',names)
    command = destination / '合并安装包.command'
    command.write_text(merger)
    command.chmod(command.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    for name in ['安装与使用说明.md', 'THIRD_PARTY_NOTICES.md']:
        if (source.parent/name).is_file(): shutil.copy2(source.parent/name, destination/name)
    for path in source.parent.glob('PaperBridge-*.zip'):
        shutil.copy2(path, destination/path.name)
    return manifest
