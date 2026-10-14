"""Remove reproducible work after a task, preserving the editable final result."""
import json
import re
import shutil
import time
from pathlib import Path

ARCHIVE_NAME = re.compile(r"\d{8}-\d{6}-[a-f0-9]{8}")
ARCHIVE_FILES = {"job.json", "translated.pdf", "bilingual.pdf", "quality.json",
                 "paragraph-cache.json", "document-terminology.json"}
TEMP_FILES = {"translated.new.pdf", "bilingual.new.pdf", "translated.part.pdf",
              "bilingual.part.pdf", "translated.compact.pdf", "bilingual.compact.pdf",
              "translated.part.compact.pdf", "cancel.request"}


def history_candidates(folder, job, *, succeeded):
    """Return only identified automatic backups with a checked current result."""
    folder = Path(folder)
    valid = (succeeded and job.get("status") == "complete" and job.get("has_output")
             and not job.get("cancel_requested")
             and not (job.get("export_report") or {}).get("layout_test")
             and (job.get("export_report") or {}).get("structural_checks_passed") is True
             and all((folder / name).is_file() and not (folder / name).is_symlink()
                     and (folder / name).stat().st_size > 0
                     for name in ["original.pdf", "translated.pdf", "bilingual.pdf"]))
    history = folder / "history"
    if not valid or not history.is_dir() or history.is_symlink():
        return []
    candidates = []
    for archive in sorted(history.iterdir()):
        if not ARCHIVE_NAME.fullmatch(archive.name) or not archive.is_dir() or archive.is_symlink():
            continue
        metadata = archive / "job.json"
        try:
            archived = json.loads(metadata.read_text()) if not metadata.is_symlink() else None
            if not isinstance(archived, dict) or archived.get("id") != job["id"]:
                continue
        except (OSError, ValueError):
            continue
        if any(p.name not in ARCHIVE_FILES or not p.is_file() or p.is_symlink() for p in archive.iterdir()):
            continue
        candidates.append(archive)
    return candidates


def cleanup_after_task(folder, job, *, succeeded, prune_history=True, force=False, remove_temporary=True):
    """Call only after the worker/export has stopped using this job directory.

    Incomplete tasks keep their prior versions and paragraph records for retry.
    A successful checked export may discard software-created rollback copies.
    Unknown files, directories, and symlinks are never treated as old versions.
    """
    folder = Path(folder)
    report = {"enabled": force or job.get("settings", {}).get("auto_cleanup", True),
              "finished_at": time.time(), "removed_files": 0, "removed_bytes": 0,
              "removed_paths": [], "errors": [], "old_versions_removed": 0}
    if not report["enabled"]:
        report["status"] = "disabled"
        return report
    if folder.is_symlink() or not folder.is_dir():
        report.update(status="partial", errors=["任务目录不可安全清理"])
        return report

    def remove(path, *, directory=False):
        if path.is_symlink():
            report["errors"].append(f"保留链接：{path.name}")
            return False
        if not path.exists():
            return True
        if path.is_dir() and not directory:
            report["errors"].append(f"保留未知目录：{path.name}")
            return False
        try:
            files = [p for p in path.rglob("*") if p.is_file() and not p.is_symlink()] if path.is_dir() else [path]
            sizes = sum(p.stat().st_size for p in files)
            count = len(files)
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            report["removed_files"] += count
            report["removed_bytes"] += sizes
            report["removed_paths"].append(str(path.relative_to(folder)))
            return True
        except OSError as exc:
            report["errors"].append(f"{path.name}：{type(exc).__name__}")
            return False

    if remove_temporary:
        remove(folder / "layout-work", directory=True)
        for name in TEMP_FILES:
            remove(folder / name)
    try:
        history = folder / "history"
        if prune_history:
            for archive in history_candidates(folder, job, succeeded=succeeded):
                if remove(archive, directory=True):
                    report["old_versions_removed"] += 1
                    for key in ["translation_baseline", "repair_baseline"]:
                        if job.get(key) == str(archive.relative_to(folder)):
                            job.pop(key, None)
            try:
                history.rmdir()
            except OSError:
                pass
    except OSError as exc:
        report["errors"].append(f"检查旧版本：{type(exc).__name__}")
    report["status"] = "partial" if report["errors"] else "complete"
    return report
