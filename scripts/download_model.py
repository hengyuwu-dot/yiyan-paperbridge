"""One-time weights download; never receives manuscript content."""
import json
import hashlib
import os
import sys
import time
import urllib.request
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import fcntl
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["HF_HOME"] = str(ROOT / ".cache" / "huggingface")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_HUB_OFFLINE"] = "0"
os.environ["TRANSFORMERS_OFFLINE"] = "0"


def parallel_download(url, destination, expected_size, progress):
    chunk_size = 8 * 1024 * 1024
    chunks = destination.parent / (destination.name + ".chunks")
    chunks.mkdir(exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".download")
    # Salvage fully downloaded leading chunks from a previous sequential run.
    if partial.exists():
        with partial.open("rb") as handle:
            for number in range(partial.stat().st_size // chunk_size):
                part = chunks / str(number)
                data = handle.read(chunk_size)
                if not part.exists():
                    part.write_bytes(data)
    count = (expected_size + chunk_size - 1) // chunk_size
    completed, last_message = 0, 0
    lock = threading.Lock()
    def fetch(number):
        nonlocal completed, last_message
        start, end = number * chunk_size, min(expected_size - 1, (number + 1) * chunk_size - 1)
        part = chunks / str(number)
        size = end - start + 1
        if not (part.exists() and part.stat().st_size == size):
            error = None
            for attempt in range(7):
                try:
                    request = urllib.request.Request(url + f"&part={number}", headers={"Range": f"bytes={start}-{end}"})
                    with urllib.request.urlopen(request, timeout=60) as response:
                        if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{expected_size}":
                            raise RuntimeError("模型仓库不支持安全分段下载")
                        data = response.read(size + 1)
                    if len(data) != size:
                        raise RuntimeError("分段下载不完整")
                    temp = part.with_suffix(".tmp")
                    temp.write_bytes(data)
                    temp.replace(part)
                    error = None
                    break
                except Exception as exc:
                    error = exc
                    time.sleep(min(10, 1 + attempt * 2))
            if error:
                raise error
        with lock:
            completed += size
            if progress and time.monotonic() - last_message > 15:
                progress(f"下载 {destination.name}：{completed / 1e6:.0f} / {expected_size / 1e6:.0f} MB")
                last_message = time.monotonic()
    workers = min(36, max(1, int(os.environ.get("PAPERBRIDGE_DOWNLOAD_WORKERS", "12"))))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(fetch, number) for number in range(count)]):
            future.result()
    with partial.open("wb") as handle:
        for number in range(count):
            handle.write((chunks / str(number)).read_bytes())
    return partial, chunks


def install(progress=None, model_id=None, model_dir=None):
    model_root = ROOT / "models"
    model_root.mkdir(exist_ok=True)
    with (model_root / ".installation.lock").open("w") as lock:
        if progress:
            progress("正在准备模型；如已有下载任务，会等待它完成")
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _install(progress, model_id, model_dir)


def _install(progress=None, model_id=None, model_dir=None):
    from paperbridge.translator import MODEL_ID as DEFAULT_ID, MODEL_DIR as DEFAULT_DIR
    MODEL_ID = model_id or DEFAULT_ID
    MODEL_DIR = Path(model_dir or DEFAULT_DIR)
    if progress:
        progress("正在连接模型仓库，仅下载模型文件")
    with urllib.request.urlopen(f"https://huggingface.co/api/models/{MODEL_ID}?blobs=true", timeout=45) as response:
        info = json.load(response)
    revision = info["sha"]
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    files = [f for f in info["siblings"] if f["rfilename"].endswith((".json", ".safetensors", ".model", ".txt")) or f["rfilename"] in {"README.md", "LICENSE"}]
    records = []
    for entry in files:
        name = entry["rfilename"]
        if "/" in name or name.startswith("."):
            continue
        destination = MODEL_DIR / name
        expected_size = entry.get("size", 0)
        expected_hash = entry.get("lfs", {}).get("sha256")
        def digest(path):
            hasher = hashlib.sha256()
            with path.open("rb") as handle:
                while chunk := handle.read(4 * 1024 * 1024):
                    hasher.update(chunk)
            return hasher.hexdigest()
        if not (destination.exists() and destination.stat().st_size == expected_size and (not expected_hash or digest(destination) == expected_hash)):
            partial = destination.with_suffix(destination.suffix + ".download")
            url = f"https://huggingface.co/{MODEL_ID}/resolve/{revision}/{quote(name)}?download=true"
            if expected_size > 64 * 1024 * 1024:
                partial, chunks = parallel_download(url, destination, expected_size, progress)
                if digest(partial) != expected_hash:
                    raise RuntimeError("模型文件 SHA256 校验失败")
                partial.replace(destination)
                for part in chunks.iterdir():
                    part.unlink()
                chunks.rmdir()
                records.append({"file": name, "size": expected_size, "sha256": digest(destination)})
                continue
            error = None
            for attempt in range(3):
                try:
                    offset = partial.stat().st_size if partial.exists() else 0
                    request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
                    with urllib.request.urlopen(request, timeout=60) as response:
                        if response.status != 206:
                            offset = 0
                        received, last_message = offset, 0
                        with partial.open("ab" if offset else "wb") as handle:
                            while chunk := response.read(1024 * 1024):
                                handle.write(chunk)
                                received += len(chunk)
                                if progress and time.monotonic() - last_message > 15:
                                    progress(f"下载 {name}：{received / 1e6:.0f} / {expected_size / 1e6:.0f} MB")
                                    last_message = time.monotonic()
                    if partial.stat().st_size != expected_size:
                        raise RuntimeError("模型文件大小校验失败")
                    if expected_hash and digest(partial) != expected_hash:
                        partial.unlink()
                        raise RuntimeError("模型文件 SHA256 校验失败")
                    partial.replace(destination)
                    error = None
                    break
                except Exception as exc:
                    error = exc
            if error:
                raise error
        records.append({"file": name, "size": expected_size, "sha256": digest(destination)})
    # A ready marker is written only after the full snapshot completes.
    (MODEL_DIR / "installation.json").write_text(json.dumps({"repo": MODEL_ID, "revision": revision, "files": records}, indent=2), encoding="utf-8")
    if progress:
        progress("模型安装完成，可以离线翻译")
    return revision


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--precision", action="store_true")
    args = parser.parse_args()
    options = {"model_id": "Qwen/Qwen3-14B-MLX-4bit", "model_dir": ROOT / "models/qwen3-14b"} if args.precision else {}
    print("下载本地精译模型，约 7.9 GB；论文不会被上传。" if args.precision else "下载本地标准模型，约 2.3 GB；论文不会被上传。", flush=True)
    print("下载完成，版本：" + install(lambda message: print(message, flush=True), **options), flush=True)
