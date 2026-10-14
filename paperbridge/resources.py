"""Cheap process RSS measurements; do not load MLX to read idle memory."""
import gc
import time

import psutil


def memory_usage():
    try:
        parent = psutil.Process()
        backend = parent.memory_info().rss
        workers = 0
        count = 0
        for child in parent.children(recursive=True):
            try:
                workers += child.memory_info().rss
                count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue
        return {"available": True, "rss_bytes": backend + workers,
                "backend_bytes": backend, "worker_bytes": workers,
                "child_processes": count, "measured_at": time.time(),
                "scope": "backend_and_children"}
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return {"available": False, "rss_bytes": None}


def release_idle_memory(translator):
    translator.unload()
    from .pdf_engine import PDF_LOCK
    import pymupdf as fitz
    with PDF_LOCK:
        fitz.TOOLS.store_shrink(100)
    gc.collect()
