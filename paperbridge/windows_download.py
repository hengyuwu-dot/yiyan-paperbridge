"""Download only pinned public GGUF weights, verifying before activation."""
import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.request

from .windows_models import REQUIREMENTS, manifest, model_directory, profile_for


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(4 * 1024**2):
            value.update(chunk)
    return value.hexdigest()


def install_gguf(progress=None, model_dir=None):
    directory = Path(model_dir or model_directory("standard"))
    directory.mkdir(parents=True, exist_ok=True)
    profile = profile_for(directory)
    entry = manifest()[profile]
    target = directory / entry["file"]
    if target.is_file() and target.stat().st_size == entry["bytes"] and digest(target) == entry["sha256"]:
        activate(directory, entry)
        return entry["revision"]
    partial = target.with_suffix(".gguf.download")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > entry["bytes"]:
        partial.unlink()
        offset = 0
    needed = entry["bytes"] - offset + 2 * 1024**3
    if shutil.disk_usage(directory).free < needed:
        raise RuntimeError("模型所在磁盘空间不足，请先在资源与清理中整理空间")
    url = f"https://huggingface.co/{entry['repo']}/resolve/{entry['revision']}/{entry['file']}?download=true"
    if offset < entry["bytes"]:
        error = None
        for attempt in range(4):
            offset = partial.stat().st_size if partial.exists() else 0
            try:
                request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
                with urllib.request.urlopen(request, timeout=60) as response:
                    if response.status == 206:
                        expected = f"bytes {offset}-{entry['bytes'] - 1}/{entry['bytes']}"
                        if response.headers.get("Content-Range") != expected:
                            raise RuntimeError("模型下载的续传范围异常")
                    else:
                        offset = 0
                    received = offset
                    last = 0
                    with partial.open("ab" if offset else "wb") as output:
                        while chunk := response.read(1024**2):
                            output.write(chunk)
                            received += len(chunk)
                            if received > entry["bytes"]:
                                raise RuntimeError("模型下载大小异常")
                            if progress and time.monotonic() - last > 1:
                                progress(f"下载 {REQUIREMENTS[profile]['label']}：{received / 1e9:.2f} / {entry['bytes'] / 1e9:.2f} GB")
                                last = time.monotonic()
                if received != entry["bytes"]:
                    raise RuntimeError("模型尚未下载完整")
                error = None
                break
            except Exception as exc:
                error = exc
                if attempt < 3:
                    time.sleep(2)
        if error:
            raise error
    if progress:
        progress("正在校验模型完整性，完成后即可离线翻译")
    if digest(partial) != entry["sha256"]:
        partial.unlink(missing_ok=True)
        raise RuntimeError("模型校验失败，请重新下载")
    partial.replace(target)
    activate(directory, entry)
    if progress:
        progress("模型已就绪，可以开始翻译")
    return entry["revision"]


def activate(directory, entry):
    marker = directory / "installation.json"
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps({**entry, "format": "gguf", "quantization": "Q4_K_M",
                                     "files": [{"file": entry["file"], "size": entry["bytes"], "sha256": entry["sha256"]}]}, indent=2), encoding="utf-8")
    temporary.replace(marker)
