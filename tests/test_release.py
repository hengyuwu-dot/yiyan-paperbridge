"""Release artifacts must reconstruct exactly and detect incomplete downloads."""
import hashlib
import json
import subprocess

from scripts.split_release import split_release


def test_release_parts_reconstruct_exactly_and_detect_corruption(tmp_path):
    source = tmp_path / 'Yiyan-test.dmg'
    original = bytes(range(256)) * 13
    source.write_bytes(original)
    output = tmp_path / 'release-parts'
    manifest = split_release(source, output, part_size=600)
    assert all(row['bytes'] <= 600 for row in manifest['parts'])
    rebuilt = b''.join((output / row['file']).read_bytes() for row in manifest['parts'])
    assert rebuilt == original
    assert hashlib.sha256(rebuilt).hexdigest() == manifest['sha256']
    assert json.loads((output / 'PARTS.json').read_text()) == manifest
    check = ['/usr/bin/shasum', '-a', '256', '-c', 'PARTS-SHA256.txt']
    assert subprocess.run(check, cwd=output, capture_output=True).returncode == 0
    (output / manifest['parts'][1]['file']).write_bytes(b'corrupted')
    assert subprocess.run(check, cwd=output, capture_output=True).returncode != 0
