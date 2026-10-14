from pathlib import Path

import pymupdf as fitz
import pytest

from paperbridge.full_worker import publish_export
from paperbridge.reference_restore import restore_reference_text, _same_reference_appearance


def reference_pdf(path, *, color=(0, 0, 0), link=True, shift=0):
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=400)
        page.insert_text((40 + shift, 80), "Smith (2020)", color=color)
        if link:
            page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(38, 66, 120, 84),
                              "uri": "https://example.invalid/reference"})
        doc.save(path)


@pytest.mark.parametrize("change", ["white_text", "missing_link"])
def test_reference_restore_preserves_visible_text_and_links(tmp_path, change):
    source, target = tmp_path / "source.pdf", tmp_path / "target.pdf"
    reference_pdf(source)
    reference_pdf(target, color=(1, 1, 1) if change == "white_text" else (0, 0, 0), link=False)
    original_bytes = source.read_bytes()
    region = fitz.Rect(30, 50, 160, 100)
    restored = restore_reference_text(source, target, [{"page": 1, "bbox": list(region)}])
    assert len(restored) == 1
    with fitz.open(source) as before, fitz.open(target) as after:
        assert before[0].get_pixmap(clip=region).samples == after[0].get_pixmap(clip=region).samples
        assert [link.get("uri") for link in after[0].get_links()] == ["https://example.invalid/reference"]
        assert after[0].get_text().count("Smith") == 1
    assert source.read_bytes() == original_bytes


def test_reference_tolerance_cannot_accept_invisible_or_recoloured_text(tmp_path):
    paths = [tmp_path / f"{name}.pdf" for name in ("source", "white", "blue", "shifted")]
    reference_pdf(paths[0])
    reference_pdf(paths[1], color=(1, 1, 1))
    reference_pdf(paths[2], color=(0, 0, 1))
    reference_pdf(paths[3], shift=0.01)
    region = fitz.Rect(30, 50, 160, 100)
    with fitz.open(paths[0]) as original:
        for path in paths[1:3]:
            with fitz.open(path) as changed:
                assert not _same_reference_appearance(original[0], changed[0], region)
        with fitz.open(paths[3]) as shifted:
            assert _same_reference_appearance(original[0], shifted[0], region)


@pytest.mark.parametrize("prior_output", [False, True])
def test_export_publication_rolls_back_a_midway_file_failure(tmp_path, monkeypatch, prior_output):
    staging, folder = tmp_path / "staging", tmp_path / "job"
    staging.mkdir()
    folder.mkdir()
    names = ("translated.pdf", "bilingual.pdf", "quality.json")
    for name in names:
        (staging / name).write_bytes(b"new-" + name.encode())
        if prior_output:
            (folder / name).write_bytes(b"old-" + name.encode())
    (folder / "original.pdf").write_bytes(b"original source")
    replace = Path.replace

    def fail_second_file(self, target):
        if self == staging / "bilingual.pdf":
            raise OSError("simulated publishing failure")
        return replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_second_file)
    with pytest.raises(OSError, match="publishing failure"):
        publish_export(staging, folder)
    for name in names:
        if prior_output:
            assert (folder / name).read_bytes() == b"old-" + name.encode()
        else:
            assert not (folder / name).exists()
    assert (folder / "original.pdf").read_bytes() == b"original source"


def test_export_requires_all_artifacts_before_touching_old_files(tmp_path):
    staging, folder = tmp_path / "staging", tmp_path / "job"
    staging.mkdir()
    folder.mkdir()
    (staging / "translated.pdf").write_bytes(b"new")
    (folder / "translated.pdf").write_bytes(b"old")
    with pytest.raises(FileNotFoundError):
        publish_export(staging, folder)
    assert (folder / "translated.pdf").read_bytes() == b"old"
