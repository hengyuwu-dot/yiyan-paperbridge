"""Local disk accounting and narrowly scoped optional cache cleanup."""
import copy
import json
import os
import re
import shutil
import stat
import threading
import time
from pathlib import Path
from contextlib import contextmanager

from .file_lock import lock_file, unlock_file
from .storage_cleanup import TEMP_FILES, history_candidates

CHOICES = [
    {"id": "memory", "name": "闲置内存", "description": "释放模型、推理及页面预览缓存；不会释放硬盘空间", "default": True},
    {"id": "temporary", "name": "临时排版文件", "description": "移除可重新生成的排版缓存与未完成临时 PDF", "default": True},
    {"id": "backups", "name": "旧自动备份", "description": "仅清理已有新版并通过检查的自动备份；未完成任务的上一版保留", "default": True},
    {"id": "downloads", "name": "下载缓存", "description": "移除安装缓存和模型下载碎片；中断下载需重新获取已清理部分", "default": False},
    {"id": "logs", "name": "运行日志", "description": "移除运行与失败诊断日志；清理后无法查看这些旧诊断", "default": False},
]
GROUPS = {"models": "本地翻译模型", "runtime": "运行环境", "layout": "排版模型与字体",
          "papers": "论文、译稿及任务记录", "other": "程序、缓存及其他"}
_scan_lock = threading.Lock()
_snapshot = None
_snapshot_key = None


def disk_usage(root):
    try:
        usage = shutil.disk_usage(root)
        return {"available": True, "total_bytes": usage.total, "used_bytes": usage.used,
                "free_bytes": usage.free, "measured_at": time.time()}
    except OSError:
        return {"available": False}


def safe_path(root, path):
    """No symlink in any ancestor may redirect cleanup outside this root."""
    root, path = Path(root).absolute(), Path(path).absolute()
    try:
        path.relative_to(root)
    except ValueError:
        return False
    current = path
    while True:
        if current.is_symlink():
            return False
        if current == current.parent:
            return True
        current = current.parent


def file_stats(path, errors):
    """Yield regular files without following links; tolerate files disappearing."""
    path = Path(path)
    if path.is_symlink():
        return
    if path.is_dir():
        def failed(exc):
            errors.append(f"读取目录：{type(exc).__name__}")
        for folder, dirs, files in os.walk(path, followlinks=False, onerror=failed):
            dirs[:] = [name for name in dirs if not (Path(folder) / name).is_symlink()]
            for name in files:
                item = Path(folder) / name
                try:
                    info = item.lstat()
                    if stat.S_ISREG(info.st_mode):
                        yield item, info
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    errors.append(f"读取文件：{type(exc).__name__}")
    else:
        try:
            info = path.lstat()
            if stat.S_ISREG(info.st_mode):
                yield path, info
        except FileNotFoundError:
            pass
        except OSError as exc:
            errors.append(f"读取文件：{type(exc).__name__}")


def measure(paths, errors):
    seen = set()
    result = {"bytes": 0, "logical_bytes": 0, "files": 0}
    for path in paths:
        for _, info in file_stats(path, errors):
            key = info.st_dev, info.st_ino
            if key in seen:
                continue
            seen.add(key)
            # Removing only one hard link may free no blocks. Be conservative.
            result["bytes"] += getattr(info, "st_blocks", (info.st_size + 511) // 512) * 512 if info.st_nlink == 1 else 0
            result["logical_bytes"] += info.st_size
            result["files"] += 1
    return result


def job_folders(data):
    data = Path(data)
    if data.is_symlink() or not data.is_dir():
        return
    for folder in sorted(data.iterdir()):
        if not re.fullmatch(r"[0-9a-f]{32}", folder.name) or not safe_path(data, folder) or not folder.is_dir():
            continue
        metadata = folder / "job.json"
        if metadata.is_symlink():
            continue
        try:
            job = json.loads(metadata.read_text())
            if isinstance(job, dict) and job.get("id") == folder.name:
                yield folder, job
        except (OSError, ValueError):
            continue


def cleanup_targets(root, data):
    """Preview and cleanup share this allowlist; never accept caller paths."""
    root, data = Path(root), Path(data)
    groups = {choice["id"]: [] for choice in CHOICES}
    errors = []
    try:
        entries = list(job_folders(data))
    except OSError as exc:
        errors.append(f"读取任务目录：{type(exc).__name__}")
        entries = []
    for folder, job in entries:
        groups["temporary"].extend([folder / "layout-work", *(folder / name for name in TEMP_FILES)])
        try:
            groups["backups"].extend(history_candidates(folder, job, succeeded=job.get("status") == "complete"))
        except OSError as exc:
            errors.append(f"读取旧备份：{type(exc).__name__}")
        groups["logs"].append(folder / "full-worker.log")
        failures = folder / "translation-failures"
        if safe_path(data, failures) and failures.is_dir():
            try:
                groups["logs"].extend(p for p in failures.iterdir() if re.fullmatch(r"[0-9a-f]{20}\.json", p.name))
            except OSError as exc:
                errors.append(f"读取诊断日志：{type(exc).__name__}")
    groups["logs"].append(root / "tmp" / "layout-install.log")
    groups["downloads"].append(root / ".cache" / "pip")
    for model in [root / "models" / "qwen3-4b", root / "models" / "qwen3-14b"]:
        if not safe_path(root, model) or not model.is_dir():
            continue
        try:
            model_files = list(model.iterdir())
        except OSError as exc:
            errors.append(f"读取下载缓存：{type(exc).__name__}")
            continue
        for path in model_files:
            if re.fullmatch(r"[A-Za-z0-9_.-]+\.(?:safetensors|gguf)\.download", path.name):
                groups["downloads"].append(path)
            elif re.fullmatch(r"[A-Za-z0-9_.-]+\.safetensors\.chunks", path.name) and path.is_dir() and not path.is_symlink():
                try:
                    if all(re.fullmatch(r"\d+(?:\.tmp)?", p.name) and p.is_file() and not p.is_symlink() for p in path.iterdir()):
                        groups["downloads"].append(path)
                except OSError as exc:
                    errors.append(f"读取下载分段：{type(exc).__name__}")
    for key, paths in groups.items():
        groups[key] = [p for p in paths if (safe_path(root, p) or safe_path(data, p)) and p.exists() and not p.is_symlink()]
    return groups, errors


def storage_inventory(root, data, *, refresh=False):
    """Cache the large model/runtime traversal; never read model contents."""
    global _snapshot, _snapshot_key
    root, data = Path(root), Path(data)
    bundled = os.environ.get("PAPERBRIDGE_BUNDLE_RESOURCES")
    bundle = Path(bundled) if bundled else None
    key = str(root.absolute()), str(data.absolute()), bundled
    with _scan_lock:
        if refresh or _snapshot is None or _snapshot_key != key or time.time() - _snapshot["measured_at"] >= 60:
            groups = {key: {"id": key, "name": name, "bytes": 0, "logical_bytes": 0, "files": 0} for key, name in GROUPS.items()}
            seen, errors = set(), []
            for path, info in file_stats(root, errors):
                inode = info.st_dev, info.st_ino
                if inode in seen:
                    continue
                seen.add(inode)
                parts = path.relative_to(root).parts
                category = ("models" if parts[0] == "models" else "runtime" if parts[0] == ".venv"
                            else "layout" if parts[:2] == (".cache", "babeldoc")
                            else "papers" if parts[0] in {"data", "论文PDF"} else "other")
                row = groups[category]
                row["bytes"] += getattr(info, "st_blocks", (info.st_size + 511) // 512) * 512
                row["logical_bytes"] += info.st_size
                row["files"] += 1
            # Portable app data contains only a link to its runtime. Count the
            # read-only app resources too, without adding them to cleanup paths.
            if bundle is not None and bundle.name == "Resources" and bundle.parent.name == "Contents":
                for path, info in file_stats(bundle.parent, errors):
                    inode = info.st_dev, info.st_ino
                    if inode in seen:
                        continue
                    seen.add(inode)
                    category = ("runtime" if path.is_relative_to(bundle / "Python") else
                                "models" if path.is_relative_to(bundle / "Models") else
                                "layout" if path.is_relative_to(bundle / "LayoutAssets") else "other")
                    row = groups[category]
                    row["bytes"] += getattr(info, "st_blocks", (info.st_size + 511) // 512) * 512
                    row["logical_bytes"] += info.st_size
                    row["files"] += 1
            _snapshot = {"software_bytes": sum(r["bytes"] for r in groups.values()), "groups": list(groups.values()),
                         "measured_at": time.time(), "errors": errors, "partial": bool(errors)}
            _snapshot_key = key
        result = copy.deepcopy(_snapshot)
    targets, errors = cleanup_targets(root, data)
    result["choices"] = [{**choice, **measure(targets[choice["id"]], errors)} for choice in CHOICES]
    result["errors"].extend(errors)
    result["partial"] |= bool(errors)
    result["disk"] = disk_usage(root)
    return result


def clear_optional_files(root, data, selected):
    result = {"removed_bytes": 0, "removed_allocated_bytes": 0, "removed_files": 0, "errors": []}
    if not {"downloads", "logs"} & set(selected):
        return result
    targets, errors = cleanup_targets(root, data)
    result["errors"] = errors
    for category in {"downloads", "logs"} & set(selected):
        for path in targets[category]:
            if not (safe_path(root, path) or safe_path(data, path)):
                continue
            measured = measure([path], result["errors"])
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
                result["removed_bytes"] += measured["logical_bytes"]
                result["removed_allocated_bytes"] += measured["bytes"]
                result["removed_files"] += measured["files"]
            except OSError as exc:
                result["errors"].append(f"{path.name}：{type(exc).__name__}")
    return result


@contextmanager
def download_cache_guard(root, enabled):
    """Coordinate with the resumable model downloader, including its CLI."""
    path = Path(root) / "models" / ".installation.lock"
    if not enabled or not path.parent.exists():
        yield
        return
    if not safe_path(root, path):
        raise OSError("下载锁路径不可安全访问")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "r+") as handle:
        lock_file(handle.fileno(), blocking=False)
        try:
            yield
        finally:
            unlock_file(handle.fileno())
