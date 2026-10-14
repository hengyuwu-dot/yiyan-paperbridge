"""Column-aware bibliography regions, derived from the source PDF geometry."""
import re

import pymupdf as fitz

REFERENCE_TITLE = re.compile(r"(?:\d+(?:\.\d+)*\.?\s*)?(?:references|bibliography|literature cited)", re.I)
APPENDIX_TITLE = re.compile(r"(?:appendix|appendices|supplementary material)(?:\s|[.:]).*|(?:appendix|appendices|supplementary material)", re.I)
CAPTION_START = re.compile(r"^(?:fig(?:ure)?s?\.?|table)\s+(?:[A-Z]\.)?\d+(?:\.\d+)*\s*[:.]\s", re.I)


def block_text(block):
    return " ".join("".join(s["text"] for s in line["spans"]).strip()
                    for line in block.get("lines", []))


def bibliography_block(text):
    # Author-year, numbered IEEE and Vancouver-style reference starts.
    text = re.sub(r"^(?:\[\d+\]|\d+[.)])\s*", "", text.strip())
    name = r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ’'-]+"
    return bool(re.match(rf"(?:(?:[A-Z]\.\s*){{1,3}}{name}|{name}\s*,\s*[A-Z]\.|(?:arXiv|https?://|doi:))", text)
                and re.search(r"\b(?:19|20)\d{2}[a-z]?\b|arXiv:|doi:", text))


def column_bounds(page, blocks):
    width = page.rect.width
    midpoint = width / 2
    left, right = [], []
    for block in blocks:
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"])
            if len(re.findall(r"[A-Za-z]{2,}", text)) < 3:
                continue
            x0, _, x1, _ = line["bbox"]
            if x0 < midpoint - 20 and x1 < midpoint + .03 * width:
                left.append((x0, x1))
            elif x0 > midpoint - .03 * width and x1 > midpoint + 20:
                right.append((x0, x1))
    if len(left) >= 3 and len(right) >= 3:
        gutter = (max(x[1] for x in left) + min(x[0] for x in right)) / 2
        return [(0, gutter), (gutter, width)]
    return [(0, width)]


def exclude_captions(regions, number, blocks, columns):
    """A bibliography can continue past floats; their captions remain prose.

    Remove only the caption's band in the intersecting column. This leaves
    bibliography entries above/below it and in the other column protected.
    The font-scaled guard also leaves room for the translated glyph height.
    """
    caption_blocks = []
    for block in blocks:
        # PDF extractors can merge two columns into a single physical block.
        # Group its lines by column before deciding whether it is a caption.
        grouped = {}
        for line in block['lines']:
            center = (line['bbox'][0] + line['bbox'][2]) / 2
            col = next((i for i, (left, right) in enumerate(columns) if left <= center <= right), 0)
            grouped.setdefault(col, []).append(line)
        for lines in grouped.values():
            box = fitz.Rect(lines[0]['bbox'])
            for line in lines[1:]:
                box |= fitz.Rect(line['bbox'])
            caption_blocks.append({'lines': lines, 'bbox': list(box)})
    for block in caption_blocks:
        if not CAPTION_START.match(block_text(block).strip()):
            continue
        size = max((s['size'] for line in block['lines'] for s in line['spans']), default=10)
        caption = fitz.Rect(block['bbox'])
        top, bottom = caption.y0 - .5 * size, caption.y1 + .5 * size
        updated = []
        for region in regions:
            box = fitz.Rect(region['bbox'])
            if (region['page'] != number or caption.x1 <= box.x0 or caption.x0 >= box.x1
                    or bottom <= box.y0 or top >= box.y1):
                updated.append(region)
                continue
            if top > box.y0:
                updated.append({'page': number, 'bbox': [box.x0, box.y0, box.x1, top]})
            if bottom < box.y1:
                updated.append({'page': number, 'bbox': [box.x0, bottom, box.x1, box.y1]})
        regions[:] = updated


def detect_sections(path):
    reference_regions, layouts, headings, body_pages = [], [], [], []
    in_references = False
    with fitz.open(path) as document:
        for index, page in enumerate(document):
            blocks = [b for b in page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)["blocks"]
                      if b.get("type") == 0]
            columns = column_bounds(page, blocks)
            layouts.append({"page": index + 1, "columns": columns})
            events = []
            for block in blocks:
                text = block_text(block).strip()
                kind = "references" if REFERENCE_TITLE.fullmatch(text) else "appendix" if APPENDIX_TITLE.fullmatch(text) else None
                if not kind or block["bbox"][1] < 25:
                    continue
                x = (block["bbox"][0] + block["bbox"][2]) / 2
                col = next((c for c, (a, b) in enumerate(columns) if a <= x <= b), len(columns) - 1)
                # A translated heading can be taller than the source's Roman
                # glyph box. End bibliography redaction above this small font-
                # scaled guard so it cannot delete a Chinese appendix title.
                size = max((s["size"] for line in block["lines"] for s in line["spans"]), default=10)
                safe_top = block["bbox"][1] - .4 * size if kind == "appendix" else block["bbox"][1]
                events.append((col, block["bbox"][1], kind, text, safe_top))
            events.sort()
            first_reference = next((e for e in events if e[2] == "references"), None)
            for col, (x0, x1) in enumerate(columns):
                cursor = 0
                if first_reference and col > first_reference[0]:
                    # A page can have two-column body text followed by a shared
                    # footer bibliography. Continue from the top only if this
                    # column actually starts with bibliography material.
                    bib_y = []
                    for b in blocks:
                        if not x0 <= (b["bbox"][0] + b["bbox"][2]) / 2 <= x1:
                            continue
                        text = block_text(b).strip()
                        if bibliography_block(text):
                            bib_y.append(b["bbox"][1])
                    cursor = min(bib_y) if bib_y else first_reference[1]
                for _, y, kind, text, safe_top in [e for e in events if e[0] == col]:
                    if in_references and safe_top > cursor:
                        reference_regions.append({"page": index + 1, "bbox": [x0, cursor, x1, safe_top]})
                    headings.append({"page": index + 1, "column": col, "y": y, "kind": kind, "text": text})
                    in_references = kind == "references"
                    cursor = y
                if in_references:
                    reference_regions.append({"page": index + 1, "bbox": [x0, cursor, x1, page.rect.height]})
            exclude_captions(reference_regions, index + 1, blocks, columns)
            if any(len(re.findall(r"[A-Za-z]{2,}", block_text(b))) >= 3
                   and b["bbox"][1] >= 25
                   and not is_reference_region(index + 1, b["bbox"], reference_regions)
                   for b in blocks):
                body_pages.append(index + 1)
    return {"reference_regions": reference_regions, "page_columns": layouts,
            "section_headings": headings, "body_pages": body_pages}


def is_reference_region(page, box, regions):
    rectangle = fitz.Rect(box)
    area = 0
    for region in regions:
        if region["page"] != page:
            continue
        area += (rectangle & fitz.Rect(region["bbox"])).get_area()
    return area > .6 * max(1, rectangle.get_area())
