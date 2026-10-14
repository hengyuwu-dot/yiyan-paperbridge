from pathlib import Path
import hashlib
import json
import re

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient

from paperbridge.glossary import terms_for, matched_terms, parse_custom
from paperbridge.translator import protect, restore, TranslationError
from paperbridge.pdf_engine import analyze, export_pdf, render_page
from paperbridge.app import app, parse_pages
from scripts.make_sample import make_sample


def test_numeric_and_citation_integrity():
    source = "At redshift 0.05, the 95% confidence interval includes 6000 K [1, 3]."
    protected, tokens = protect(source)
    assert restore(protected, tokens) == source
    with pytest.raises(TranslationError):
        restore(protected.replace("<PB0>", ""), tokens)
    with pytest.raises(TranslationError):
        restore(protected + "<PB0>", tokens)
    with pytest.raises(TranslationError):
        restore(protected + "<PB999>", tokens)
    identifiers="GW170817, SN2020abc, H2O and IL-6 were observed."
    protected_identifiers, codes=protect(identifiers)
    assert restore(protected_identifiers,codes)==identifiers
    assert all(code in codes.values() for code in ["GW170817","SN2020abc","H2O","IL-6"])


def test_glossary_domain_and_case_override():
    glossary = terms_for("astronomy", "Light Curve = 光度变化曲线")
    assert matched_terms("The light curve and circumstellar medium.", glossary) == {
        "circumstellar medium": "星周介质", "Light Curve": "光度变化曲线"}
    assert "luminosity" not in matched_terms("luminosity-based", {"lumin": "伪词"})
    with pytest.raises(ValueError):
        parse_custom("no separator")
    assert parse_pages("1-3,5", 5) == {1,2,3,5}
    with pytest.raises(ValueError):
        parse_pages("1-99999999", 5)


def test_original_objects_and_overflow_are_preserved(tmp_path):
    source = make_sample(tmp_path / "original.pdf")
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    result = analyze(source)
    assert result["page_count"] == 1
    assert result["pages"][0]["tables"] == 1
    assert any("含数学" in s["reason"] for s in result["segments"])
    assert any(s["kind"] == "table" and s["status"] == "pending" for s in result["segments"])
    candidates = [s for s in result["segments"] if s["status"] == "pending"]
    assert candidates
    for s in candidates:
        s.update(translation="学术论文排版测试",status="translated")
    candidates[0]["translation"] = "很长的译文" * 2000
    target, dual = tmp_path / "translated.pdf", tmp_path / "bilingual.pdf"
    report = export_pdf(source,target,dual,result["segments"])
    assert candidates[0]["id"] in report["overflow"]
    assert not candidates[0]["exported"]
    assert report["replaced"] > 0
    assert target.stat().st_size < 2 * 1024 * 1024
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
    with fitz.open(source) as a, fitz.open(target) as b, fitz.open(dual) as c:
        assert len(a) == len(b) == 1 and len(c) == 2
        assert a[0].rect == b[0].rect
        assert candidates[0]["source"] in re.sub(r"\s+"," ",b[0].get_text())
        assert "L = 4 pi R^2 sigma T^4" in b[0].get_text()
        assert "6000 K" in b[0].get_text() and "95%" in b[0].get_text()
        image_a, image_b = a[0].get_image_info(hashes=True), b[0].get_image_info(hashes=True)
        assert [(i["bbox"],i["digest"]) for i in image_a] == [(i["bbox"],i["digest"]) for i in image_b]
        # Pixel equality of the complete figure including its labels.
        clip = fitz.Rect(310,258,550,408)
        assert a[0].get_pixmap(clip=clip).samples == b[0].get_pixmap(clip=clip).samples
        assert len(a[0].get_drawings()) == len(b[0].get_drawings())
        for x,y in [(310,518),(430,570),(550,622)]:
            clip = fitz.Rect(x-1,y-1,x+1,y+1)
            assert a[0].get_pixmap(clip=clip).samples == b[0].get_pixmap(clip=clip).samples
    assert render_page(target,1).startswith(b"\x89PNG")
    with pytest.raises(ValueError): render_page(target,2)


def test_scanned_and_password_protected_documents(tmp_path):
    scanned = tmp_path / "scan.pdf"
    with fitz.open() as doc:
        page=doc.new_page()
        image = fitz.Pixmap(fitz.csRGB,fitz.IRect(0,0,20,20),False)
        image.clear_with(240)
        page.insert_image(page.rect,stream=image.tobytes("png"))
        doc.save(scanned)
    analysis = analyze(scanned)
    assert analysis["pages"][0]["scanned"] and analysis["warnings"]
    encrypted = tmp_path / "protected.pdf"
    with fitz.open() as doc:
        doc.new_page()
        doc.save(encrypted,encryption=fitz.PDF_ENCRYPT_AES_256,owner_pw="owner",user_pw="test")
    with pytest.raises(ValueError,match="加密"):
        analyze(encrypted)


def test_local_http_validation(tmp_path, monkeypatch):
    import paperbridge.app as module
    monkeypatch.setattr(module,"DATA",tmp_path)
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/api/status").json()["offline"] is True
    assert client.post("/api/documents",content=b"fake",headers={"X-Filename":"a.pdf"}).status_code == 400
    assert client.post("/api/model/install",headers={"Origin":"https://untrusted.example"}).status_code == 403
    assert client.get("/api/status",headers={"Host":"untrusted.example"}).status_code == 400
    sample=make_sample(tmp_path / "test.pdf")
    response=client.post("/api/documents",content=sample.read_bytes(),headers={"X-Filename":"paper.pdf"})
    assert response.status_code == 200
    job=response.json()
    assert client.get(f"/api/documents/{job['id']}/page/1").headers["content-type"] == "image/png"
    assert client.get(f"/api/documents/{job['id']}/download/original").content == sample.read_bytes()
    assert client.get(f"/api/documents/{job['id']}/segments").json()
    assert client.get(f"/api/documents/{job['id']}/download/translated").status_code == 404


def test_hyperlink_and_rotated_page_are_preserved(tmp_path):
    source = tmp_path / "linked.pdf"
    with fitz.open() as doc:
        p=doc.new_page(width=400,height=500)
        p.insert_text((50,100),"Scientific observation",fontsize=12)
        p.insert_link({"kind":fitz.LINK_URI,"from":fitz.Rect(50,84,170,103),"uri":"https://example.org/article"})
        p.set_rotation(90)
        doc.save(source)
    result=analyze(source)
    seg=next(s for s in result["segments"] if s["status"]=="pending")
    seg.update(status="translated",translation="科学观测")
    target,dual=tmp_path / "zh.pdf",tmp_path / "dual.pdf"
    export_pdf(source,target,dual,result["segments"])
    with fitz.open(source) as a,fitz.open(target) as b:
        assert b[0].rotation==a[0].rotation==90
        assert b[0].rect==a[0].rect
        assert b[0].get_links()[0]["uri"]==a[0].get_links()[0]["uri"]
        assert b[0].get_links()[0]["from"]==a[0].get_links()[0]["from"]


def test_existing_redaction_annotation_cannot_remove_source_content(tmp_path):
    source=tmp_path / "annotated.pdf"
    with fitz.open() as doc:
        page=doc.new_page()
        page.insert_text((50,100),"Preserve this scientific statement",fontsize=12)
        page.add_redact_annot(fitz.Rect(50,84,250,104))
        doc.save(source)
    result=analyze(source)
    assert result["warnings"]
    assert all(s["status"]=="preserved" for s in result["segments"])
    target,dual=tmp_path / "zh.pdf",tmp_path / "dual.pdf"
    export_pdf(source,target,dual,result["segments"])
    with fitz.open(target) as doc:
        assert "Preserve this scientific statement" in doc[0].get_text()
        assert len(list(doc[0].annots()))==1


def test_reference_column_does_not_skip_later_body(tmp_path):
    source = tmp_path / "reference-column.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 100), "Source\nReferences", fontsize=10)
        page.insert_text((50, 180), "Later scientific discussion must be translated", fontsize=10)
        page.insert_text((50, 250), "References", fontsize=10)
        page.insert_text((50, 300), "Author et al. Journal citation", fontsize=10)
        doc.save(source)
    segments = analyze(source)["segments"]
    body = next(s for s in segments if "Later scientific discussion" in s["source"])
    citation = next(s for s in segments if "Journal citation" in s["source"])
    assert body["status"] == "pending"
    assert citation["reason"] == "参考文献保留原文"


def test_small_overlap_cannot_erase_adjacent_formula(tmp_path):
    source = tmp_path / "adjacent-formula.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 100), "Formula = 0 - 1" + " " * 10 + "for the observed case", fontsize=14)
        page.insert_text((50, 113), "period of four years", fontsize=10)
        doc.save(source)
    result = analyze(source)
    segment = next(s for s in result["segments"] if "period of four years" in s["source"])
    # Simulate a valid model output: export still has to protect neighbouring glyphs.
    segment.update(translation="四年的观测周期", status="translated")
    target, dual = tmp_path / "zh.pdf", tmp_path / "dual.pdf"
    report = export_pdf(source, target, dual, result["segments"])
    assert segment["id"] in report["protected_overlap"]
    assert not segment["exported"]
    with fitz.open(source) as a, fitz.open(target) as b:
        assert a[0].get_pixmap().samples == b[0].get_pixmap().samples


def test_scientific_terms_quantities_and_layout_tokens():
    text = "Kirchhoff–Fresnel diffraction predicts tens of thousands of signals {v1} (Abbott et al. 2021)."
    protected, tokens = protect(text, matched_terms(text, terms_for('astronomy')))
    restored = restore(protected, tokens)
    assert '基尔霍夫–菲涅耳 衍射' in restored
    assert '数万' in restored and '{v1}' in restored
    assert '(Abbott et al. 2021)' in restored
    with pytest.raises(TranslationError):
        restore(protected.replace(next(k for k,v in tokens.items() if v=='{v1}'), ''), tokens)
    with pytest.raises(TranslationError):
        restore(protected + ' 100000', tokens)


def test_manual_full_paragraph_edit_preserves_formula_and_numbers():
    from paperbridge.full_worker import validate_edit
    source = 'The amplification is {v1}, with 95% confidence (2024).'
    validate_edit(source, '放大率为 {v1}，置信度为 95%（2024）。')
    with pytest.raises(ValueError, match='公式'):
        validate_edit(source, '放大率为常数，置信度为 95%（2024）。')
    with pytest.raises(ValueError, match='数值'):
        validate_edit(source, '放大率为 {v1}，置信度为 99%（2024）。')


def test_failed_polish_cannot_publish_missing_numbers(monkeypatch):
    from paperbridge.translator import LocalTranslator
    local = LocalTranslator()
    monkeypatch.setattr(local, 'load', lambda: None)
    calls = []
    def fake_generate(messages, max_tokens):
        calls.append(messages)
        if len(calls) == 1:
            return '根据观测分析，检出率可能为 <PB0>，需进一步分析这些观测结果以确认结论。'
        return '检出率为 <PB0>，概率达到 100%。'
    monkeypatch.setattr(local, '_generate', fake_generate)
    value, notes = local.translate('The detection rate may be 95% according to the observations, although further analysis is needed to establish the conclusion.', '', '通用科研', {}, True)
    assert '95%' in value and '100' not in value and '可能' in value
    assert any('初译' in note for note in notes)
    from paperbridge.review import has_issues
    assert has_issues({'source': 'The detection rate may be 95%.', 'translation': value, 'notes': notes}, [])
    assert not any('科学含义仍需人工核对' in note for note in notes)


def test_numbers_cannot_move_out_of_explicit_bound():
    from paperbridge.translator import check_quantitative_limits
    source = 'Models include terms only up to <PB0>PN.'
    check_quantitative_limits(source, '模型仅考虑到<PB0>PN阶的项。')
    with pytest.raises(TranslationError, match='上下限'):
        check_quantitative_limits(source, '展开至高阶PN项十分繁琐。文献讨论了<PB0>PN阶。')


def test_vector_check_accepts_float_rounding_but_detects_movement(tmp_path):
    from paperbridge.quality import inspect_pdf
    source, close, moved = [tmp_path / name for name in ['a.pdf', 'b.pdf', 'c.pdf']]
    for p, delta in [(source, 0), (close, .00008), (moved, 2)]:
        with fitz.open() as doc:
            page = doc.new_page()
            page.draw_line((20 + delta, 30), (100 + delta, 30))
            doc.save(p)
    assert inspect_pdf(source, close, [])['structural_checks_passed']
    assert not inspect_pdf(source, moved, [])['structural_checks_passed']


def test_figure_restoration_never_reverts_a_translated_form(tmp_path):
    from paperbridge.graphics import restore_untouched_forms
    source, target = tmp_path / 'source.pdf', tmp_path / 'target.pdf'
    with fitz.open() as child, fitz.open() as document:
        page = child.new_page(width=100, height=100)
        page.draw_line((10, 10), (90, 90))
        parent = document.new_page(width=200, height=200)
        parent.show_pdf_page(fitz.Rect(30, 30, 130, 130), child, 0)
        document.save(source)
    target.write_bytes(source.read_bytes())
    with fitz.open(target) as document:
        # Change the drawing inside the nested form, as the layout engine does.
        xref = document[0].get_xobjects()[-1][0]
        changed = document.xref_stream(xref).replace(b'10', b'20')
        document.update_stream(xref, changed)
        document.saveIncr()
    restore_untouched_forms(source, target, [{'source_xref': xref, 'translation': '中文正文'}])
    with fitz.open(target) as document:
        assert document.xref_stream(xref) == changed
    restore_untouched_forms(source, target, [{'source_xref': xref, 'translation': ''}])
    with fitz.open(source) as original, fitz.open(target) as document:
        assert document.xref_stream(xref) == original.xref_stream(xref)


def test_alternating_export_reuses_resources_without_changing_any_page(tmp_path):
    from paperbridge.graphics import make_alternating_pdf
    from random import Random
    source,target,dual=[tmp_path/name for name in ['original.pdf','translated.pdf','dual.pdf']]
    pix=fitz.Pixmap(fitz.csRGB,128,128,Random(123).randbytes(128*128*3),False)
    for path,label in [(source,'Original'),(target,'Translation')]:
        with fitz.open() as doc:
            image_xref=0
            for n in range(12):
                page=doc.new_page(width=200,height=250)
                page.insert_text((10,20),f'{label} {n}')
                image_xref=page.insert_image(fitz.Rect(20,40,180,200),pixmap=pix,xref=image_xref)
            doc.save(path,deflate=True)
    make_alternating_pdf(source,target,dual)
    assert dual.stat().st_size < 2*(source.stat().st_size + target.stat().st_size)
    with fitz.open(source) as original,fitz.open(target) as chinese,fitz.open(dual) as bilingual:
        assert len(bilingual)==24
        assert len({image[0] for page in bilingual for image in page.get_images()})<=2
        for n in range(12):
            assert bilingual[2*n].get_pixmap().samples==original[n].get_pixmap().samples
            assert bilingual[2*n+1].get_pixmap().samples==chinese[n].get_pixmap().samples


def test_table_identifiers_are_preserved_but_prose_and_headers_translate():
    from paperbridge.layout_policy import literal_reason
    for text in ['EMBS (Wempe et al. 2022)', 'Oguri (2018)', '(Dominik et al. 2013)',
                 'LIGO A{v1}', 'EPL', 'CE{v1}ET', '{v1}Hz{v2}', 'ln ({v1}){v2}']:
        assert literal_reason(text, 'fallback_line'), text
    for text in ['References', 'Lensing Model', 'Source', 'Detector',
                 'The rate may be high (Oguri 2018).', 'Einstein Telescope detects events']:
        assert not literal_reason(text, 'fallback_line'), text


def test_frequency_prefix_and_catalog_version_are_atomic():
    text, values = protect('deci-Hz detectors use GWTC-4.0, GW150914 and millihertz signals.')
    assert 'GWTC-4.0' in values.values()
    assert '分赫兹' in values.values() and '毫赫兹' in values.values()
    assert '0' not in values.values()


def test_citation_protection_does_not_hide_scientific_explanations():
    original = '(e.g., Wong et al. 2020, such as the Hubble constant {v1} and density {v2})'
    protected, values = protect(original)
    assert 'Hubble constant' in protected and 'such as' in protected
    assert restore(protected, values) == original
    assert not any('Hubble constant' in value for value in values.values())
