"""Subset embedded fonts, accepting only smaller, visually identical PDFs."""
import hashlib
import time
from pathlib import Path

import pymupdf as fitz


def _links(page):
    return [{k: v for k, v in link.items() if k not in {"xref", "id"}}
            for link in page.get_links()]


def _images(document, page):
    return sorted(hashlib.sha256(document.xref_stream(image[0])).digest()
                  for image in page.get_images())


def verify_identical(before, after):
    """Check every page without keeping rendered pages resident in memory."""
    if len(before) != len(after) or before.metadata != after.metadata or before.get_toc() != after.get_toc():
        raise ValueError("PDF 页面或文档信息发生变化")
    for old, new in zip(before, after):
        if (old.rect != new.rect or old.mediabox != new.mediabox or old.cropbox != new.cropbox
                or old.rotation != new.rotation or old.get_text() != new.get_text()
                or _links(old) != _links(new) or _images(before, old) != _images(after, new)):
            raise ValueError(f"第 {old.number + 1} 页内容检查未通过")
        # Compare lossless RGB pixels, including figures, tables and formulae.
        matrix = fitz.Matrix(1.5, 1.5)
        expected = old.get_pixmap(matrix=matrix, alpha=False)
        actual = new.get_pixmap(matrix=matrix, alpha=False)
        if (expected.width, expected.height, expected.samples) != (actual.width, actual.height, actual.samples):
            raise ValueError(f"第 {old.number + 1} 页外观检查未通过")


def compact_pdf(path):
    """Never publish a changed or larger result; leave the PDF intact on failure.

    Hidden layers, editable forms and annotations can contain text not seen by
    the font usage scanner. Preserve those documents without subsetting.
    """
    path = Path(path)
    started = time.monotonic()
    report = {"status": "unchanged", "before_bytes": path.stat().st_size,
              "after_bytes": path.stat().st_size, "method": "font_subset",
              "checked_pages": 0}
    temporary = path.with_suffix(".compact.pdf")
    try:
        with fitz.open(path) as original:
            if original.get_ocgs() or original.is_form_pdf or original.has_annots() or original.is_encrypted:
                report.update(status="skipped", reason="保留含图层、表单、批注或加密的文档")
                return report
            with fitz.open(path) as candidate:
                candidate.subset_fonts()
                candidate.save(temporary, garbage=4, deflate=True)
            if temporary.stat().st_size >= report["before_bytes"]:
                return report
            with fitz.open(temporary) as candidate:
                verify_identical(original, candidate)
                report["checked_pages"] = len(original)
            report.update(status="optimized", after_bytes=temporary.stat().st_size)
        temporary.replace(path)
    except Exception as exc:
        report.update(status="skipped", reason=f"已保留压缩前 PDF：{type(exc).__name__}")
    finally:
        temporary.unlink(missing_ok=True)
        report["saved_bytes"] = report["before_bytes"] - report["after_bytes"]
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return report
