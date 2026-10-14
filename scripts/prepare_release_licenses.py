"""Collect installed dependency notices and exact AGPL source distributions.

Only public software resources are fetched. No manuscript or task is accessed.
Run before a binary release; upstream source availability is verified by SHA256.
"""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request
import time

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "release-assets"


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        chunks, count, last = [], 0, time.monotonic()
        while chunk := response.read(1024 * 1024):
            chunks.append(chunk); count += len(chunk)
            if time.monotonic() - last > 20:
                print(f"Downloading public source: {count / 1e6:.1f} MB", flush=True)
                last = time.monotonic()
        return b''.join(chunks)


def main():
    packages = ROOT / ".venv/lib/python3.12/site-packages"
    licenses = ASSETS / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    rows = []
    for dist in sorted(metadata.distributions(path=[str(packages)]), key=lambda d: d.metadata['Name'].lower()):
        name, version = dist.metadata['Name'], dist.version
        info = licenses / f"{name}-{version}"
        info.mkdir(exist_ok=True)
        (info / "METADATA.txt").write_text(dist.read_text('METADATA') or '', encoding="utf-8")
        found = []
        for entry in dist.files or []:
            relative = Path(entry)
            if '__pycache__' in relative.parts or relative.suffix == '.pyc':
                continue
            if not any(p.lower().startswith(('license', 'copying', 'notice', 'copyright', 'authors')) for p in relative.parts):
                continue
            source = Path(dist.locate_file(entry))
            if not source.is_file() or '..' in relative.parts:
                continue
            dest = info / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            found.append(str(relative))
        rows.append({'name': name, 'version': version, 'license': dist.metadata.get('License-Expression') or dist.metadata.get('License'),
                     'project_urls': dist.metadata.get_all('Project-URL', []), 'license_files': found})
    (ASSETS / "DEPENDENCIES.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))

    sources = ASSETS / "vendor-sources"
    sources.mkdir(exist_ok=True)
    manifest = []
    for name in ['BabelDOC', 'PyMuPDF', 'Levenshtein', 'flatbuffers', 'sentencepiece', 'tokenizers']:
        version = metadata.version(name)
        data = json.loads(fetch(f"https://pypi.org/pypi/{name}/{version}/json"))
        source = next((file for file in data['urls'] if file['packagetype'] == 'sdist'), None)
        if source is None:
            repos = {'flatbuffers': 'google/flatbuffers', 'sentencepiece': 'google/sentencepiece',
                     'tokenizers': 'huggingface/tokenizers'}
            repo = repos[name]
            source = {'filename': f'{name}-{version}-source.tar.gz',
                      'url': f'https://api.github.com/repos/{repo}/tarball/v{version}', 'digests': {}}
        target = sources / source['filename']
        expected = source['digests'].get('sha256')
        if not target.exists() or expected and hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            content = fetch(source['url'])
            if expected and hashlib.sha256(content).hexdigest() != expected:
                raise RuntimeError(f"Source checksum failed: {name}")
            target.write_bytes(content)
        manifest.append({'name': name, 'version': version, 'file': target.name, 'url': source['url'],
                         'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'pypi_checksum_verified': expected is not None})
        # Some wheels omit a top-level license file. Preserve the matching
        # upstream source license as well as the complete source distribution.
        with tarfile.open(target) as archive:
            for member in archive.getmembers():
                path = Path(member.name)
                if member.isfile() and any(p.lower().startswith(('license', 'copying', 'notice', 'copyright')) for p in path.parts):
                    dest = licenses / f'{name}-{version}' / 'upstream-source' / path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(archive.extractfile(member).read())
        print(f"Collected corresponding source: {target.name}", flush=True)
    import pymupdf
    version = pymupdf.VersionFitz
    mupdf = sources / f'mupdf-{version}-source.tar.gz'
    url = f'https://mupdf.com/downloads/archive/mupdf-{version}-source.tar.gz'
    if not mupdf.exists():
        mupdf.write_bytes(fetch(url))
    # Fail closed on a HTML error page masquerading as a source archive.
    with tarfile.open(mupdf) as archive:
        if not any(m.name.endswith('/source/fitz/context.c') for m in archive.getmembers()):
            raise RuntimeError('MuPDF corresponding source archive is incomplete')
    manifest.append({'name': 'MuPDF', 'version': version, 'file': mupdf.name, 'url': url,
                     'sha256': hashlib.sha256(mupdf.read_bytes()).hexdigest()})
    # CPython's source includes the full PSF license and stdlib notices.
    python_source = sources / 'Python-3.12.14.tgz'
    url = 'https://www.python.org/ftp/python/3.12.14/Python-3.12.14.tgz'
    if not python_source.exists():
        python_source.write_bytes(fetch(url))
    with tarfile.open(python_source) as archive:
        for member in archive.getmembers():
            parts = Path(member.name).parts
            if member.isfile() and len(parts) > 1 and (parts[1] == 'LICENSE' or parts[1] == 'LICENSES'):
                target = licenses / 'Python-3.12.14' / Path(*parts[1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
    manifest.append({'name': 'CPython', 'version': '3.12.14', 'file': python_source.name, 'url': url,
                     'sha256': hashlib.sha256(python_source.read_bytes()).hexdigest()})
    # Standalone CPython embeds C libraries. Keep the build project's complete
    # collected notices in addition to CPython's own PSF and stdlib notices.
    build_source = sources / 'python-build-standalone-source.tar.gz'
    build_url = 'https://codeload.github.com/astral-sh/python-build-standalone/tar.gz/refs/heads/main'
    if not build_source.exists():
        build_source.write_bytes(fetch(build_url))
    with tarfile.open(build_source) as archive:
        for member in archive.getmembers():
            parts = Path(member.name).parts
            if member.isfile() and '..' not in parts and ('licenses' in parts or path_name_is_license(parts[-1])):
                relative = Path(*parts[parts.index('licenses') + 1:]) if 'licenses' in parts else Path(parts[-1])
                dest = licenses / 'python-build-standalone' / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.extractfile(member).read())
    manifest.append({'name': 'python-build-standalone build recipes and license collection',
                     'file': build_source.name, 'url': build_url,
                     'sha256': hashlib.sha256(build_source.read_bytes()).hexdigest()})
    (sources / 'SOURCES.json').write_text(json.dumps(manifest, indent=2))
    print(f"Collected licenses for {len(rows)} distributions")


def path_name_is_license(name):
    return name.lower().startswith(('license', 'copying', 'notice', 'copyright')) or name == 'python-licenses.rst'


if __name__ == '__main__':
    main()
