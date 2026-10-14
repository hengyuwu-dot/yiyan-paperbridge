"""Reuse untouched figure form streams instead of flattening image transforms."""
import re

import pymupdf as fitz


def restore_untouched_forms(source, target, segments):
    changed = {s.get("source_xref") for s in segments
               if re.search(r"[\u3400-\u9fff]", s.get("translation", ""))}
    restored = set()
    with fitz.open(source) as original, fitz.open(target) as output:
        expected = {xref for page in original for xref, *_ in page.get_xobjects()}
        present = {xref for page in output for xref, *_ in page.get_xobjects()}
        for xref in expected & present - changed:
            # The pinned pipeline retains original xrefs (skip_clean=True).
            # Refuse to copy when another object now occupies the identifier.
            if original.xref_get_key(xref, "Subtype") != ("name", "/Form"):
                continue
            if output.xref_get_key(xref, "Subtype") != ("name", "/Form"):
                continue
            if original.xref_get_key(xref, "BBox") != output.xref_get_key(xref, "BBox"):
                continue
            output.update_object(xref, original.xref_object(xref))
            output.update_stream(xref, original.xref_stream(xref))
            restored.add(xref)
        if restored:
            output.saveIncr()
    return sorted(restored)


def make_alternating_pdf(source, translated, target):
    with fitz.open(source) as original, fitz.open(translated) as chinese, fitz.open() as dual:
        if len(original) != len(chinese):
            raise ValueError("原文与译文页数不一致，无法生成逐页对照")
        for number in range(len(original)):
            final = number == len(original) - 1
            # Retain each source's object map between page insertions. Resetting
            # it on every page embeds shared fonts/images over and over again.
            dual.insert_pdf(original, from_page=number, to_page=number, final=final)
            dual.insert_pdf(chinese, from_page=number, to_page=number, final=final)
        dual.save(target, garbage=4, deflate=True)
