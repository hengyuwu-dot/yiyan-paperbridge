"""Assemble a Windows x64 portable app with Python, CPU/CUDA and local layout."""
import argparse
import hashlib
import json
import importlib.metadata as metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist/windows/Yiyan"
CACHE = ROOT / ".cache/windows-build"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while data := f.read(4 * 1024**2):
            h.update(data)
    return h.hexdigest()


def download(url, target, expected=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and (not expected or digest(target) == expected):
        return
    print("Downloading " + target.name, flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "PaperBridge-Windows-build"})
    with urllib.request.urlopen(request, timeout=120) as response, target.with_suffix(".download").open("wb") as f:
        shutil.copyfileobj(response, f)
    temporary = target.with_suffix(".download")
    if expected and digest(temporary) != expected:
        raise RuntimeError("Checksum mismatch: " + target.name)
    temporary.replace(target)


def extract(archive, folder):
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            target = (folder / entry.filename).resolve()
            if not target.is_relative_to(folder.resolve()):
                raise ValueError("Unsafe archive member")
        z.extractall(folder)


def copy(source, destination):
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "bin", "obj"))
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def corresponding_sources(packages, assets):
    notices = assets / "windows-licenses"
    rows = []
    distributions = {d.metadata['Name'].lower(): d for d in metadata.distributions(path=[str(packages)])}
    for name, dist in sorted(distributions.items()):
        found = []
        for entry in dist.files or []:
            relative = Path(entry)
            if '..' in relative.parts or not any(p.lower().startswith(('license', 'copying', 'notice', 'copyright')) for p in relative.parts):
                continue
            source = Path(dist.locate_file(entry))
            if source.is_file():
                copy(source, notices / f'{name}-{dist.version}' / relative)
                found.append(relative.as_posix())
        rows.append({'name': name, 'version': dist.version, 'license_files': found})
    sources = assets / "vendor-sources"
    sources.mkdir(parents=True, exist_ok=True)
    records = []
    for name in ('babeldoc', 'pymupdf', 'levenshtein'):
        dist = distributions[name]
        with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{dist.version}/json', timeout=60) as response:
            info = json.load(response)
        source = next(f for f in info['urls'] if f['packagetype'] == 'sdist')
        target = sources / source['filename']
        download(source['url'], target, source['digests']['sha256'])
        records.append({'name': name, 'version': dist.version, 'url': source['url'], 'sha256': digest(target)})
    import pymupdf
    version = pymupdf.VersionFitz
    mupdf = sources / f'mupdf-{version}-source.tar.gz'
    url = f'https://mupdf.com/downloads/archive/mupdf-{version}-source.tar.gz'
    download(url, mupdf)
    import tarfile
    with tarfile.open(mupdf) as archive:
        if not any(m.name.endswith('/source/fitz/context.c') for m in archive.getmembers()):
            raise RuntimeError('Incomplete MuPDF corresponding source')
    records.append({'name': 'MuPDF', 'version': version, 'url': url, 'sha256': digest(mupdf)})
    notices.mkdir(parents=True, exist_ok=True)
    (notices / 'DEPENDENCIES.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    (sources / 'WINDOWS-SOURCES.json').write_text(json.dumps(records, indent=2), encoding='utf-8')


def build():
    if sys.platform != "win32":
        raise RuntimeError("Build this app on Windows x64")
    CACHE.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    python = OUTPUT / "Runtime/Python"
    embedded = CACHE / "python-3.12.10-embed-amd64.zip"
    download("https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip", embedded)
    extract(embedded, python)
    packages = python / "Lib/site-packages"
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "--target", str(packages),
                    "-r", str(ROOT / "requirements.windows.txt")], check=True)
    (python / "python312._pth").write_text("python312.zip\n.\nLib/site-packages\n../../Engine\nimport site\n", encoding="utf-8")
    engine = OUTPUT / "Engine"
    for name in ("paperbridge", "scripts", "desktop", "tests", "docs", "release-assets", "examples", "LICENSE", "THIRD_PARTY_NOTICES.md", "README.md", "requirements.txt", "requirements.windows.txt"):
        copy(ROOT / name, engine / name)
    corresponding_sources(packages, engine / 'release-assets')
    seed = ROOT / ".cache/babeldoc"
    if not (seed / "ready.json").is_file():
        raise RuntimeError("Install layout assets before packaging")
    copy(seed, engine / ".cache/babeldoc")
    runtime = json.loads((ROOT / "release-assets/windows-runtime.json").read_text())
    for entry in runtime["assets"]:
        archive = CACHE / entry["name"]
        download(entry["url"], archive, entry["sha256"])
        kind = "cpu" if "win-cpu" in entry["name"] else "cuda"
        extract(archive, OUTPUT / "Runtime/llama" / kind)
    for kind in ("cpu", "cuda"):
        folder = OUTPUT / "Runtime/llama" / kind
        servers = list(folder.rglob("llama-server.exe"))
        if len(servers) != 1:
            raise RuntimeError("Missing native llama-server: " + kind)
        if servers[0].parent != folder:
            for path in list(servers[0].parent.iterdir()):
                copy(path, folder / path.name)
    # Include matching llama.cpp source and its MIT notice alongside the engine.
    source = CACHE / ("llama.cpp-" + runtime["tag"] + ".zip")
    download("https://github.com/ggml-org/llama.cpp/archive/refs/tags/" + runtime["tag"] + ".zip", source)
    copy(source, engine / "release-assets/vendor-sources" / source.name)
    python_source = CACHE / "Python-3.12.10.tgz"
    download("https://www.python.org/ftp/python/3.12.10/Python-3.12.10.tgz", python_source)
    copy(python_source, engine / "release-assets/vendor-sources" / python_source.name)
    subprocess.run(["dotnet", "publish", str(ROOT / "desktop/windows/PaperBridge.csproj"),
                    "-c", "Release", "-r", "win-x64", "--self-contained", "true",
                    "-p:PublishSingleFile=true", "-p:IncludeNativeLibrariesForSelfExtract=true",
                    "-o", str(OUTPUT)], check=True)
    copy(ROOT / "docs/WINDOWS_INSTALL.md", OUTPUT / "Windows-安装教程.md")
    report = {"platform": "Windows x64", "version": "1.5.0", "models": "user_selects_4B_or_14B",
              "format": "GGUF Q4_K_M", "context_tokens": 8192, "runtime": runtime,
              "python_version": "3.12.10", "python_archive_sha256": digest(embedded),
              "python_source_sha256": digest(python_source), "llama_source_sha256": digest(source)}
    (OUTPUT / "BUILD-REPORT.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    subprocess.run([str(python / "python.exe"), "-X", "utf8", "-c",
                    "import paperbridge.app, paperbridge.full_worker; print('Embedded Windows engine imports passed')"],
                   cwd=engine, check=True)
    print("Windows application assembled: " + str(OUTPUT), flush=True)


def archive():
    target = ROOT / "dist/windows/Yiyan-1.5.0-Windows-x64.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for item in sorted(OUTPUT.rglob("*")):
            if item.is_file() and "__pycache__" not in item.parts:
                z.write(item, "Yiyan/" + item.relative_to(OUTPUT).as_posix())
    if target.stat().st_size >= 2_000_000_000:
        raise RuntimeError("Portable archive exceeds the release-asset budget")
    target.with_suffix(".zip.sha256").write_text(digest(target) + "  " + target.name + "\n", encoding="utf-8")
    print(f"Portable archive: {target.name} ({target.stat().st_size:,} bytes)", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["build", "archive"])
    if parser.parse_args().phase == "build":
        build()
    else:
        archive()
