"""Restore protected bibliography text from native PDF commands, not glyphs."""
from collections import defaultdict
from pathlib import Path

import pymupdf as fitz


def _same_pixels(source, target, region):
    options = {"matrix": fitz.Matrix(1.25, 1.25), "clip": region, "alpha": False}
    first, second = source.get_pixmap(**options), target.get_pixmap(**options)
    return (first.width, first.height, first.n, first.samples) == (second.width, second.height, second.n, second.samples)


def _same_reference_text_and_positions(source, target, region, tolerance=0.2):
    """Accept harmless rasterization differences when protected text is unchanged.

    Sub-pixel font rendering can make otherwise identical bibliography text fail
    a pixel-for-pixel comparison. Require the same extracted words in the same
    order and keep each word's box within a small PDF-point tolerance.
    """
    source_words = source.get_text("words", clip=region)
    target_words = target.get_text("words", clip=region)
    if len(source_words) != len(target_words):
        return False
    for original, rendered in zip(source_words, target_words):
        if original[4] != rendered[4]:
            return False
        if any(abs(original[index] - rendered[index]) > tolerance for index in range(4)):
            return False
    return True


def _reference_glyphs(page, region):
    result = []
    # Unlike get_texttrace(), this extraction respects Form XObject clipping.
    for block in page.get_text("rawdict", clip=region)["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                font = span["font"].split("+", 1)[-1]
                style = (font, span["color"], span.get("alpha", 255), span.get("char_flags"), line["dir"])
                for char in span["chars"]:
                    result.append((char["c"], style, span["size"], char["origin"], char["bbox"]))
    return result


def _same_reference_appearance(source, target, region):
    """Allow only sub-pixel rerasterization of otherwise identical glyphs.

    This is used after native restoration, never as a text-only fast path.
    Both images must fit the other's one-pixel neighbourhood at 2x resolution,
    so invisible text, colour changes and missing visible content still fail.
    """
    if not _same_reference_text_and_positions(source, target, region):
        return False
    first, second = _reference_glyphs(source, region), _reference_glyphs(target, region)
    if not first or len(first) != len(second):
        return False
    for original, rendered in zip(first, second):
        if original[:2] != rendered[:2] or abs(original[2] - rendered[2]) > 0.01:
            return False
        if any(abs(a - b) > 0.2 for a, b in zip((*original[3], *original[4]), (*rendered[3], *rendered[4]))):
            return False
    import numpy as np
    from PIL import Image, ImageFilter
    options = {"matrix": fitz.Matrix(2, 2), "clip": region, "alpha": False, "colorspace": fitz.csRGB}
    pixels = [page.get_pixmap(**options) for page in (source, target)]
    if (pixels[0].width, pixels[0].height) != (pixels[1].width, pixels[1].height):
        return False
    images = [Image.frombytes("RGB", (pix.width, pix.height), pix.samples) for pix in pixels]
    for image, other in (images, images[::-1]):
        values = np.asarray(image, dtype=np.int16)
        lower = np.asarray(other.filter(ImageFilter.MinFilter(3)), dtype=np.int16)
        upper = np.asarray(other.filter(ImageFilter.MaxFilter(3)), dtype=np.int16)
        if np.any(values < lower - 2) or np.any(values > upper + 2):
            return False
    return True


def _region_links(page, regions):
    return [item for item in page.get_links() if item["kind"] in {fitz.LINK_URI, fitz.LINK_GOTO}
            and any(fitz.Rect(item["from"]).intersects(region) for region in regions)]


def _same_links(source, target, region):
    def signatures(page):
        result = []
        for item in _region_links(page, [region]):
            location = tuple(round(v, 3) for v in item["from"])
            destination = tuple(round(v, 3) for v in item.get("to", ()))
            result.append((item["kind"], location, item.get("uri", ""), item.get("page", -1), destination))
        return sorted(result)
    return signatures(source) == signatures(target)


def _native_page(source, number, remove_graphics):
    copy = fitz.open()
    copy.insert_pdf(source, from_page=number, to_page=number, links=False, annots=False)
    page = copy[0]
    page.add_redact_annot(page.rect, fill=None)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE,
                          graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED if remove_graphics else fitz.PDF_REDACT_LINE_ART_NONE,
                          text=fitz.PDF_REDACT_TEXT_NONE)
    return copy


def restore_reference_text(source_path, target_path, reference_regions):
    """Keep body edits and images; restore only regions that differ visually.

    Native text retains original fonts and character advances. Images are
    removed from the graft to avoid hidden, duplicated image instances. Existing
    target images and vector graphics stay in place. A graphics fallback is
    available only for regions without images. Every restored region must pass
    exact pixels or the glyph/style and sub-pixel raster check before publishing.
    """
    grouped = defaultdict(list)
    for item in reference_regions:
        grouped[item["page"] - 1].append(fitz.Rect(item["bbox"]))
    restored = []
    target_path = Path(target_path)
    temporary = target_path.with_suffix(".references.new.pdf")
    with fitz.open(source_path) as source, fitz.open(target_path) as target:
        for number, regions in sorted(grouped.items()):
            original, page = source[number], target[number]
            changed = [region for region in regions
                       if not _same_pixels(original, page, region) or not _same_links(original, page, region)]
            if not changed:
                continue
            links = _region_links(original, changed)
            for item in _region_links(page, changed):
                page.delete_link(item)
            with _native_page(source, number, remove_graphics=True) as native:
                for region in changed:
                    page.add_redact_annot(region, fill=None)
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                      graphics=fitz.PDF_REDACT_LINE_ART_NONE, text=fitz.PDF_REDACT_TEXT_REMOVE)
                for region in changed:
                    page.show_pdf_page(region, native, 0, clip=region, keep_proportion=False, overlay=True)
            remaining = [region for region in changed if not _same_pixels(original, page, region)
                         and not _same_reference_appearance(original, page, region)]
            if remaining:
                images = [fitz.Rect(item["bbox"]) for item in original.get_image_info()]
                if any(image.intersects(region) for image in images for region in remaining):
                    raise RuntimeError("参考文献区域未通过原稿像素核对；该区域同时包含图片，已停止覆盖导出")
                with _native_page(source, number, remove_graphics=False) as native:
                    for region in remaining:
                        page.add_redact_annot(region, fill=(1, 1, 1))
                    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                          graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED, text=fitz.PDF_REDACT_TEXT_REMOVE)
                    for region in remaining:
                        page.show_pdf_page(region, native, 0, clip=region, keep_proportion=False, overlay=True)
            for item in links:
                # Copy only standard hyperlinks and in-document destinations.
                page.insert_link({key: value for key, value in item.items() if key in {"kind", "from", "uri", "page", "to", "zoom"}})
            if any(not _same_pixels(original, page, region)
                   and not _same_reference_appearance(original, page, region) for region in changed):
                raise RuntimeError("参考文献区域未通过原稿像素核对，已停止覆盖导出")
            restored.extend({"page": number + 1, "bbox": list(region)} for region in changed)
        if restored:
            target.save(temporary, garbage=4, deflate=True)
    if restored:
        temporary.replace(target_path)
    return restored
