from dataclasses import dataclass

import pymupdf as fitz

from paperbridge.il_snapshot import snapshot_graph
from paperbridge.sections import detect_sections, is_reference_region


def test_deep_pdf_snapshot_has_no_recursion_or_shared_mutable_boxes():
    @dataclass(slots=True)
    class Node:
        children: list
        box: dict
    root = Node([], {"x": 1.5})
    current = root
    for _ in range(2500):
        child = Node([], root.box)
        current.children.append(child)
        current = child
    current.children.append(root)
    copy = snapshot_graph(root)
    assert copy is not root and copy.box is not root.box
    current = copy
    for _ in range(2500):
        current = current.children[0]
        assert current.box is copy.box
    assert current.children[0] is copy
    copy.box["x"] = 9
    assert root.box["x"] == 1.5


def _columns(page, left_heading=False, right_heading=False, right_bibliography=False):
    for x in [40, 320]:
        for y in [70, 90, 110]:
            text = "A. Smith, Scientific Journal 25, 3 (2020)" if x == 320 and right_bibliography else "These scientific words establish a column"
            page.insert_text((x, y), text, fontsize=9)
    if left_heading:
        page.insert_text((40, 200), "References", fontsize=11)
    if right_heading:
        page.insert_text((320, 200), "References", fontsize=11)


def test_reference_start_in_right_column_does_not_hide_left_body(tmp_path):
    path = tmp_path / "two-col.pdf"
    with fitz.open() as doc:
        p = doc.new_page(width=600, height=800)
        _columns(p, right_heading=True)
        p.insert_text((40, 450), "A conclusion still belongs to the left column", fontsize=9)
        p.insert_text((320, 450), "Author published this journal citation", fontsize=9)
        doc.new_page(width=600, height=800)
        doc.save(path)
    regions = detect_sections(path)["reference_regions"]
    assert not is_reference_region(1, [40, 435, 255, 453], regions)
    assert is_reference_region(1, [320, 435, 555, 453], regions)
    assert is_reference_region(2, [40, 50, 200, 100], regions)


def test_reference_start_in_left_column_protects_right_from_top(tmp_path):
    path = tmp_path / "left-ref.pdf"
    with fitz.open() as doc:
        p = doc.new_page(width=600, height=800)
        _columns(p, left_heading=True, right_bibliography=True)
        doc.save(path)
    regions = detect_sections(path)["reference_regions"]
    assert not is_reference_region(1, [40, 65, 255, 113], regions)
    assert is_reference_region(1, [320, 65, 555, 113], regions)


def test_appendix_after_references_is_translatable(tmp_path):
    path = tmp_path / "appendix.pdf"
    with fitz.open() as doc:
        p = doc.new_page()
        p.insert_text((40, 150), "References", fontsize=11)
        p.insert_text((40, 190), "Author and journal citation", fontsize=9)
        p = doc.new_page()
        p.insert_text((40, 150), "Appendix A. Additional derivations", fontsize=11)
        p.insert_text((40, 190), "The following derivation is scientific body text", fontsize=9)
        doc.save(path)
    sections = detect_sections(path)
    assert is_reference_region(1, [40, 175, 250, 193], sections["reference_regions"])
    assert not is_reference_region(2, [40, 175, 280, 193], sections["reference_regions"])
    assert 2 in sections["body_pages"]


def test_same_column_appendix_has_room_for_taller_translated_heading(tmp_path):
    path = tmp_path / "reference-appendix-boundary.pdf"
    with fitz.open() as doc:
        p = doc.new_page()
        p.insert_text((40, 150), "References", fontsize=11)
        p.insert_text((40, 190), "Smith, A., Scientific Journal (2020)", fontsize=9)
        p.insert_text((40, 250), "Appendix A: Testing the pipeline", fontsize=9)
        p.insert_text((40, 280), "These additional scientific results belong to the appendix.", fontsize=9)
        doc.save(path)
    sections = detect_sections(path)
    heading = next(h for h in sections["section_headings"] if h["kind"] == "appendix")
    end = max(r["bbox"][3] for r in sections["reference_regions"])
    assert end <= heading["y"] - 3
    assert is_reference_region(1, [40, 175, 250, 193], sections["reference_regions"])
    assert not is_reference_region(1, [40, heading["y"] - 2, 300, heading["y"] + 10], sections["reference_regions"])


def test_float_caption_after_references_does_not_hide_later_bibliography(tmp_path):
    path = tmp_path / "reference-float.pdf"
    with fitz.open() as doc:
        p = doc.new_page()
        p.insert_text((40, 100), "References", fontsize=11)
        p = doc.new_page()
        p.insert_text((40, 150), "Fig. A.1: Measurements of the scientific sample.", fontsize=9)
        p.insert_text((40, 190), "Smith, A., Scientific Journal (2020)", fontsize=9)
        doc.save(path)
    sections = detect_sections(path)
    assert not is_reference_region(2, [40, 140, 270, 153], sections['reference_regions'])
    assert is_reference_region(2, [40, 180, 270, 193], sections['reference_regions'])
    assert 2 in sections['body_pages']


def test_caption_exception_keeps_adjacent_column_references_protected(tmp_path):
    path = tmp_path / "reference-float-columns.pdf"
    with fitz.open() as doc:
        p = doc.new_page(width=600, height=800)
        p.insert_text((40, 100), "References", fontsize=11)
        p = doc.new_page(width=600, height=800)
        _columns(p)
        p.insert_text((40, 200), "Smith, A., Scientific Journal (2020)", fontsize=9)
        p.insert_text((320, 200), "Table 2: Results of scientific measurements.", fontsize=9)
        doc.save(path)
    regions = detect_sections(path)['reference_regions']
    assert is_reference_region(2, [40, 190, 260, 203], regions)
    assert not is_reference_region(2, [320, 190, 550, 203], regions)


def test_author_lists_preserve_names_but_not_affiliations_or_scientific_prose():
    from paperbridge.layout_policy import frontmatter_reason
    box = [40, 150, 550, 220]
    assert frontmatter_reason("A. Smith1 · B. Jones2 · C. Brown3", 1, box, 800)
    assert frontmatter_reason("Katsuya T. Abe1, Masamune Oguri2, Simon Birrer3", 1, box, 800)
    assert not frontmatter_reason("Center for Frontier Science, Chiba University, Japan", 1, box, 800)
    assert not frontmatter_reason("A. Smith, B. Jones and C. Brown show that amplification is possible.", 1, box, 800)
    assert not frontmatter_reason("A. Smith1 · B. Jones2 · C. Brown3", 12, box, 800)
    assert frontmatter_reason("John Smith and Jane Jones", 1, box, 800)
    assert not frontmatter_reason("New York University, Charles Darwin University", 1, box, 800)


def test_citation_protection_keeps_prose_visible_before_and_after_the_year():
    from paperbridge.translator import protect, restore
    for source in [
        "(see the general algorithm analysis by Thompson et al., 2010)",
        "(Smith 2020, for a recent review of the density profile)",
        "(for AGN structure e.g. see Cackett et al., 2021)",
        "(the luminosity changed in 2020 because of an outburst)",
    ]:
        protected, tokens = protect(source)
        assert restore(protected, tokens) == source
        assert not any("algorithm analysis" in v or "density profile" in v or "AGN structure" in v or "outburst" in v for v in tokens.values())
    assert "Thompson et al., 2010" in protect("(see Thompson et al., 2010)")[1].values()
    for source in ["In 2020 the event was observed.", "Since 1987 we have used this instrument."]:
        protected, tokens = protect(source)
        assert protected.startswith(source.split()[0] + " ")
        assert restore(protected, tokens) == source


def test_mixed_font_mathematics_and_units_stay_atomic():
    from paperbridge.translator import protect, restore
    for source in ["0.{v1}M/M{v2}.21", "{v1}.5μm", "R{v1}", "H{v2}", "50-{v1}"]:
        protected, tokens = protect("The quantity is " + source + " in this case.")
        assert source in tokens.values(), (source, tokens)
        assert restore(protected, tokens) == "The quantity is " + source + " in this case."
    source = "At 7 μm and 68 per cent confidence, the emission changes."
    protected, tokens = protect(source)
    assert "μm" in tokens.values() and "68%" in tokens.values()
    assert restore(protected, tokens) == source.replace("68 per cent", "68%")
    protected, tokens = protect("where {v1}is the density and {v2}is the length")
    assert "is the density" in protected and "is the length" in protected
    protected, _ = protect("for a{v1}M{v2} black hole")
    assert "for a" in protected  # A missing PDF space must not hide the article.
    protected, tokens = protect("{v1}However, {v2}Separating the mass gives a result.")
    assert 'However' in protected and 'Separating' in protected
    assert set(tokens.values()) == {'{v1}', '{v2}'}


def test_scientific_audit_detects_reordering_but_accepts_valid_language_changes():
    from paperbridge.translation_audit import audit_translation
    source = "The mass is 0.{v1}M/M{v2}.21 at 68 per cent confidence."
    valid = "质量为0.{v1}M/M{v2}.21，置信度为68%。"
    assert not audit_translation(source, valid)
    changed = "质量为0.M{v1}/M{v2}.21，置信度为68百分之一。"
    assert {item['code'] for item in audit_translation(source, changed)} == {'math_order', 'percentage'}
    assert not audit_translation("The length is directly related to the size.", "长度与尺寸直接相关。")
    assert any(i['code'] == 'relation' for i in audit_translation("The length is directly related to the size.", "长度与尺寸成正比。"))
    assert not audit_translation("For a{v1}M{v2} black hole.", "对于质量为{v1}M{v2}的黑洞。")
    assert not audit_translation("Due to the scarcity of lensed SNe.", "由于透镜超新星数量稀少。")
    assert any(i['code'] == 'lens_source_causality' for i in audit_translation("Due to the scarcity of lensed SNe.", "由于透镜效应产生的超新星数量稀少。"))
    assert not audit_translation("The {v1}-band emission increases.", "{v1}波段的辐射增强。")
    assert any(i['code'] == 'value_as_unit' for i in audit_translation("The best-fit value is {v1}dex.", "最佳拟合值的单位为{v1}dex。"))
    assert not audit_translation("The best-fit value is {v1}dex.", "最佳拟合值为{v1}dex。")


def test_natural_footnote_detection_scales_with_page_geometry():
    from paperbridge.layout_policy import is_natural_footnote
    source = "1 This scientific explanation needs translation even in a footnote."
    assert is_natural_footnote(source, [40, 370, 300, 395], "abandon", 500)
    assert not is_natural_footnote(source, [40, 570, 300, 595], "abandon", 1000)
    assert is_natural_footnote("†This scientific explanation needs translation even in a footnote.", [40, 370, 300, 395], "abandon", 500)


def test_numbered_bibliographies_and_accented_author_names():
    from paperbridge.sections import bibliography_block
    assert bibliography_block("[1] A. Smith, Journal of Science 12, 5 (2020)")
    assert bibliography_block("25. García, J., Astronomical Review 9, 31 (1998a)")
    assert not bibliography_block("The body of this scientific paragraph cites Smith (2020).")


def test_object_identifiers_with_spaces_and_unicode_minus_are_not_translated():
    from paperbridge.layout_policy import literal_reason
    for source in ['HE 1104−1805', 'RX J1131−1231', 'SDSS J0924+0219', 'Q 2237+0305']:
        assert literal_reason(source, 'fallback_line')
    assert not literal_reason('The quasar HE 1104−1805 is magnified.', 'fallback_line')


def test_homonyms_use_physical_context_without_overriding_custom_terms():
    from paperbridge.glossary import contextual_glossary, matched_terms, normalize_line_hyphens
    text = "The lens shear and convergence are fixed while numerical convergence is tested."
    terms = contextual_glossary(text, {}, 'astronomy')
    assert matched_terms(text, terms) == {'numerical convergence': '数值收敛', 'convergence': '会聚度'}
    assert 'convergence' not in contextual_glossary("The numerical convergence is good.", {}, 'astronomy')
    assert 'convergence' not in contextual_glossary("The lens shear and convergence.", {}, 'engineering')
    assert contextual_glossary("A negative constant surface mass density conserves total convergence.", {}, 'astronomy')['convergence'] == '会聚度'
    assert contextual_glossary(text, {'Convergence':'用户认可的译名'}, 'astronomy')['Convergence'] == '用户认可的译名'
    assert normalize_line_hyphens("Stellar- mass objects show micro- lensing.", {'stellar-mass':'恒星质量'}) == "Stellar-mass objects show microlensing."
    assert normalize_line_hyphens("Microlensingvariability depends on the source.", {'microlensing variability':'微引力透镜光变'}) == "Microlensing variability depends on the source."
    assert normalize_line_hyphens("Theunmatchedword and R{v1} remain.", {'microlensing variability':'微引力透镜光变'}) == "Theunmatchedword and R{v1} remain."


def test_repair_archives_previous_outputs_and_refuses_running_jobs(tmp_path, monkeypatch):
    import json
    import paperbridge.app as module
    from fastapi.testclient import TestClient
    monkeypatch.setattr(module, 'DATA', tmp_path)
    monkeypatch.setattr(module, 'jobs', {})
    calls = []
    monkeypatch.setattr(module.executor, 'submit', lambda *a, **kw: calls.append((a, kw)))
    ident = 'a' * 32
    folder = tmp_path / ident
    folder.mkdir()
    original = b'%PDF-original-unchanged'
    previous = b'%PDF-previous-translation'
    (folder / 'original.pdf').write_bytes(original)
    (folder / 'translated.pdf').write_bytes(previous)
    job = {'id':ident, 'name':'Generic paper.pdf', 'status':'complete', 'settings':{'engine':'full', 'domain':'general', 'glossary':''},
           'has_output':True, 'segments':[{'id':'one','source':'Scientific observation','translation':'科学观测','status':'edited'}]}
    baseline = json.dumps(job)
    (folder / 'job.json').write_text(baseline)
    client = TestClient(module.app)
    response = client.post(f'/api/documents/{ident}/repair')
    assert response.status_code == 200
    record = json.loads((folder / 'job.json').read_text())
    assert record['status'] == 'queued' and record['progress'] == 0 and record['segments'] == job['segments']
    assert (folder / record['repair_baseline'] / 'translated.pdf').read_bytes() == previous
    assert (folder / record['repair_baseline'] / 'job.json').read_text() == baseline
    assert (folder / 'original.pdf').read_bytes() == original
    assert len(calls) == 1 and calls[0][1] == {'repair':True, 'run_token':record['run_token']}
    assert client.post(f'/api/documents/{ident}/repair').status_code == 409
    assert len(calls) == 1


def test_sentence_recovery_preserves_a_literal_cross_page_formula(monkeypatch):
    import json
    from paperbridge.translator import LocalTranslator, TranslationError
    local = LocalTranslator()
    monkeypatch.setattr(local, 'load', lambda: None)
    calls = []
    def generate(messages, budget):
        source = next(json.loads(line)['SOURCE'] for line in messages[-1]['content'].split('\n') if line.startswith('{') and 'SOURCE' in json.loads(line))
        calls.append(source)
        if len(source) > 120:
            raise TranslationError('incomplete paragraph output')
        reference = json.loads(messages[0]['content'].split('\n')[-1])
        assert set(reference['占位符的内容（仅供理解，译文须输出占位符本身）']) == set(__import__('re').findall(r'<PB\d+>', source))
        return '这个测量量很小。' if source.startswith('This') else '我们观测到稳定的信号。'
    monkeypatch.setattr(local, '_generate', generate)
    source = '{v1}). This measured quantity is small and is obtained directly from our measurements. We observe a stable signal in the universe over the full duration of the experiment.'
    translated, notes = local.translate(source, '', '通用科研', {}, polish=False)
    assert translated.startswith('{v1}).') and '稳定的信号' in translated
    assert len(calls) == 4  # Two whole attempts and two prose pieces, no formula inference.
    assert any('逐句' in n for n in notes)


def test_cached_translation_distinguishes_identical_text_with_different_formulas():
    from paperbridge.full_worker import translation_cache_key
    source = 'The value is {v1}.'
    first = translation_cache_key('pipeline', source, {'{v1}':'κ = 0.5'}, 'Lens equation')
    assert first != translation_cache_key('pipeline', source, {'{v1}':'γ = 0.5'}, 'Lens equation')
    assert first != translation_cache_key('pipeline', source, {'{v1}':'κ = 0.5'}, 'Numerical methods')
    assert first == translation_cache_key('pipeline', source, {'{v1}':'κ = 0.5'}, 'Lens equation')


def test_spelled_cardinal_quantities_are_protected_without_adding_free_digits():
    from paperbridge.translator import protect, restore, TranslationError
    protected, tokens = protect('We observe four galaxies and six quasars (Four et al., 2020).')
    assert '四' in tokens.values() and '六' in tokens.values()
    assert 'Four et al., 2020' in tokens.values()
    assert 'four' not in protected and 'six' not in protected
    translated = restore(protected, tokens)
    assert '四' in translated and '六' in translated
    import pytest
    with pytest.raises(TranslationError):
        restore(protected + '4', tokens)


def test_unit_protection_does_not_hide_english_pronouns_or_abbreviations():
    from paperbridge.translator import protect, restore
    from paperbridge.translation_audit import audit_translation
    source = "COSMOGRAIL’s results allow us to measure a 5 us delay, e.g. in this experiment."
    protected, tokens = protect(source)
    assert 'allow us to' in protected and 'e.g.' in protected and 'COSMOGRAIL’s' in protected
    assert 'us' in tokens.values() and 'g' not in tokens.values() and 's' not in tokens.values()
    assert restore(protected, tokens) == source
    assert 'us' in protect('Time (us)')[1].values()
    assert 'e. g.' in protect('For example, e. g. a stable system.')[0]
    assert any(i['code'] == 'english_function_word' for i in audit_translation('This allows us to measure the signal.', '这允许us测量信号。'))
    assert not audit_translation('We measure a 5 us delay.', '我们测得5 us的延迟。')
    assert any(i['code'] == 'english_function_word' for i in audit_translation('This allows us to measure the signal.', '这允许 us 测量信号。'))
    assert any(i['code'] == 'possessive_suffix' for i in audit_translation('We use Moore’s law.', '我们使用摩尔定律(s)。'))
    assert any(i['code'] == 'possessive_suffix' for i in audit_translation('AB’s work and CD’s research.', 'AB’s和CD’s的研究。'))
    assert not audit_translation('Newton’s method measures time (s).', '牛顿方法测量时间(s)。')
    assert any(i['code'] == 'abbreviation_fragment' for i in audit_translation('For example, e.g. Smith.', '例如g。Smith。'))
    assert any(i['code'] == 'abbreviation_fragment' for i in audit_translation('Novel studies, e.g. population studies.', '新研究，例如 g 群体研究。'))
    assert any(i['code'] == 'duplicate_quantity' for i in audit_translation('These two components are distinct.', '这两个两组件彼此不同。'))
    assert not audit_translation('Three triangular schemes use four quaternion components.', '三种三角形方案使用四个四元数分量。')


def test_response_format_recovery_is_limited_to_a_complete_json_terminator():
    import json
    import pytest
    from paperbridge.translator import parse_model_response, restore, TranslationError
    valid = '{"translation":"图<PB0>展示了“微”尺度的信号。"}'
    smart = '{"translation":"图<PB0>展示了“微”尺度的信号。”}'
    assert parse_model_response(smart) == parse_model_response(valid)
    assert parse_model_response(smart[:-2] + '“}') == parse_model_response(valid)
    assert restore(parse_model_response(smart)['translation'], {'<PB0>':'2'}) == '图2展示了“微”尺度的信号。'
    for incomplete in ['{"translation":"信号。', '{"translation":"信号。”', '说明文字 {"translation":"信号。”}', '{"translation":"信号。"} trailing']:
        with pytest.raises(json.JSONDecodeError):
            parse_model_response(incomplete)
    # A syntactically recovered response must still fail if a quantity is lost.
    with pytest.raises(TranslationError):
        restore(parse_model_response('{"translation":"图展示信号。”}')['translation'], {'<PB0>':'2'})
    with pytest.raises(TranslationError):
        restore('图<PB0>的信号<PB数字>。', {'<PB0>':'2'})


def test_geometrically_confirmed_footnote_label_is_kept_outside_inference(monkeypatch):
    import json
    from paperbridge.translator import LocalTranslator
    local = LocalTranslator()
    monkeypatch.setattr(local, 'load', lambda: None)
    requests = []
    def generate(messages, budget):
        source = next(json.loads(line)['SOURCE'] for line in messages[-1]['content'].split('\n') if line.startswith('{') and 'SOURCE' in json.loads(line))
        requests.append(source)
        assert source == 'This parameter is <PB0>.'
        return '这个参数为<PB0>。'
    monkeypatch.setattr(local, '_generate', generate)
    result, notes = local.translate('{v1}This parameter is {v2}.', '', '通用科研', {}, False,
                                    {'{v1}':'12','{v2}':'κ = 0.5'}, footnote=True)
    assert result == '{v1} 这个参数为{v2}。'
    assert len(requests) == 1 and any('脚注编号' in n for n in notes)


def test_leading_formula_or_unconfirmed_number_remains_visible_to_model(monkeypatch):
    import json
    from paperbridge.translator import LocalTranslator
    local = LocalTranslator()
    monkeypatch.setattr(local, 'load', lambda: None)
    def generate(messages, budget):
        source = next(json.loads(line)['SOURCE'] for line in messages[-1]['content'].split('\n') if line.startswith('{') and 'SOURCE' in json.loads(line))
        assert source == '<PB0> This parameter is <PB1>.'
        return '<PB0>这个参数为<PB1>。'
    monkeypatch.setattr(local, '_generate', generate)
    for is_note, meaning in [(False, '12'), (True, 'κ = 1')]:
        result, notes = local.translate('{v1}This parameter is {v2}.', '', '通用科研', {}, False,
                                        {'{v1}':meaning,'{v2}':'κ = 0.5'}, footnote=is_note)
        assert '{v1}' in result and not any('脚注编号' in n for n in notes)


def test_sentence_recovery_retries_a_lost_citation_with_explicit_feedback(monkeypatch):
    import json
    from paperbridge.translator import LocalTranslator, TranslationError
    local = LocalTranslator()
    monkeypatch.setattr(local, 'load', lambda: None)
    calls = []
    def generate(messages, budget):
        message = messages[-1]['content']
        source = next(json.loads(line)['SOURCE'] for line in message.split('\n') if line.startswith('{') and 'SOURCE' in json.loads(line))
        calls.append(message)
        if len(source) > 120:
            raise TranslationError('whole paragraph rejected')
        if source.startswith('This'):
            if 'DRAFT' not in message:
                return '这一公式采用了已发表的结果。'
            assert '<PB0>' in message and '必须各保留一次' in message
            return '这一公式采用了<PB0>中已发表的结果。'
        return '测量结果仍然稳定。'
    monkeypatch.setattr(local, '_generate', generate)
    source = 'This formula follows the published result by Smith (2020) and is evaluated directly. Measurements remain stable throughout the full duration of the experiment.'
    result, notes = local.translate(source, '', '通用科研', {}, False)
    assert 'Smith (2020)' in result and '测量结果仍然稳定' in result
    assert len(calls) == 5  # Two paragraph attempts, one corrected sentence and the final sentence.


def test_first_page_affiliation_addresses_are_preserved_without_hiding_science():
    from paperbridge.layout_policy import frontmatter_reason
    address = '1 Department of Physics, University of Example, 10 Academic Road, New York 10027, USA'
    assert frontmatter_reason(address, 1, [40, 600, 280, 720], 800) == '作者机构与通讯地址保留原文'
    assert not frontmatter_reason(address, 2, [40, 200, 280, 260], 800)
    assert not frontmatter_reason('We measure signals using data from the University Institute at postcode 10027.', 1, [40, 200, 280, 260], 800)


def test_table_units_and_pure_citation_lists_are_preserved_across_layout_labels():
    from paperbridge.layout_policy import literal_reason
    assert literal_reason('(arcsec)', 'paragraph') == '公式函数或单位保留原文'
    assert literal_reason('{v1}deg{v2}', 'table') == '公式函数或单位保留原文'
    assert literal_reason('km s{v1}', 'paragraph') == '公式函数或单位保留原文'
    assert literal_reason('Bond {v1}(1991); Bower (1991); Lacey and Cole (1993)', 'paragraph') == '作者引文与学术名称保留原文'
    assert not literal_reason('We measure a separation in arcsec.', 'paragraph')
    assert not literal_reason('See Bond (1991); Bower (1991) for a derivation.', 'paragraph')


def test_native_reference_restoration_keeps_body_images_vectors_and_links(tmp_path):
    from io import BytesIO
    from PIL import Image
    from paperbridge.reference_restore import restore_reference_text
    region = fitz.Rect(290, 350, 590, 790)
    image = BytesIO()
    Image.new('RGB', (8, 8), '#88aacb').save(image, format='PNG')
    original, target = tmp_path / 'source.pdf', tmp_path / 'target.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        page.insert_text((40, 80), 'OLD BODY')
        page.draw_rect(fitz.Rect(280, 370, 550, 600), color=(.2,.3,.4), fill=(.8,.9,1), fill_opacity=.4)
        page.insert_image(fitz.Rect(40, 150, 80, 190), stream=image.getvalue())
        page.insert_image(fitz.Rect(420, 440, 460, 480), stream=image.getvalue())
        page.insert_text((310, 410), 'Smith (2020)', fontsize=9, color=(0,0,1))
        page.insert_link({'kind':fitz.LINK_URI, 'from':fitz.Rect(305,395,380,414), 'uri':'https://example.invalid/reference'})
        doc.save(original)
    with fitz.open(original) as source, fitz.open() as doc:
        doc.insert_pdf(source)
        page = doc[0]
        page.add_redact_annot(region, fill=None)
        page.add_redact_annot(fitz.Rect(30,60,180,100), fill=None)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE, text=fitz.PDF_REDACT_TEXT_REMOVE)
        page.insert_text((40,80), 'NEW BODY')
        page.insert_text((310.07,410), 'Smith (2020)', fontsize=9, color=(0,0,1))
        doc.save(target)
    restored = restore_reference_text(original, target, [{'page':1,'bbox':list(region)}])
    assert len(restored) == 1
    with fitz.open(original) as source, fitz.open(target) as doc:
        assert source[0].get_pixmap(clip=region).samples == doc[0].get_pixmap(clip=region).samples
        assert len(doc[0].get_image_info()) == len(source[0].get_image_info()) == 2
        assert len(doc[0].get_drawings()) == len(source[0].get_drawings()) == 1
        assert 'NEW BODY' in doc[0].get_text() and 'OLD BODY' not in doc[0].get_text()
        assert doc[0].get_text().count('Smith') == 1
        assert any(item.get('uri') == 'https://example.invalid/reference' for item in doc[0].get_links())
    assert restore_reference_text(original, target, [{'page':1,'bbox':list(region)}]) == []


def test_sentence_correction_also_preserves_a_quantitative_lower_bound(monkeypatch):
    import json
    from paperbridge.translator import LocalTranslator, TranslationError
    local = LocalTranslator()
    monkeypatch.setattr(local, 'load', lambda: None)
    corrected = []
    def generate(messages, budget):
        message = messages[-1]['content']
        source = next(json.loads(line)['SOURCE'] for line in message.split('\n') if line.startswith('{') and 'SOURCE' in json.loads(line))
        if len(source) > 120:
            raise TranslationError('paragraph recovery needed')
        if source.startswith('We'):
            if 'DRAFT' not in message:
                return '我们需要<PB0>个独立观测。'
            corrected.append(message)
            assert '上下限' in message
            return '我们需要至少<PB0>个独立观测。'
        return '在整个实验期间，测量结果都保持稳定。'
    monkeypatch.setattr(local, '_generate', generate)
    source = 'We need at least 5 independent observations to estimate the uncertainty from the data. Measurements remain stable throughout the entire duration of this experiment.'
    result, _ = local.translate(source, '', '通用科研', {}, False)
    assert '至少5个' in result and len(corrected) == 1


def test_formula_whitespace_and_adjacent_indices_are_atomic_but_prose_is_visible():
    from paperbridge.translator import protect, restore, check_quantitative_limits
    from paperbridge.translation_audit import audit_translation
    source = 'The magnification is μ {v1}.7 and the error is N{v2}i j.'
    valid = '放大率为μ{v1}.7，误差为N{v2}ij。'
    assert not audit_translation(source, valid)
    assert any(i['code'] == 'math_order' for i in audit_translation(source, '放大率为μ{v1}.7，误差为N{v2}ji。'))
    protected, tokens = protect(source)
    assert 'μ {v1}.7' in tokens.values() and 'N{v2}i j' in tokens.values()
    assert restore(protected, tokens) == source
    prose, _ = protect('The value {v1} is a measured quantity.')
    assert 'is a measured quantity' in prose
    check_quantitative_limits('up to <PB0>', '质量高达<PB0>。')
    import pytest
    with pytest.raises(Exception):
        check_quantitative_limits('up to <PB0>', '质量超过<PB0>。')


def test_clipped_last_line_suffix_is_merged_without_widening_the_column():
    from types import SimpleNamespace as NS
    from paperbridge.layout_policy import merge_edge_fragments
    def para(text, x0, x1, bottom, top, label='plain text'):
        return NS(unicode=text, box=NS(x=x0,x2=x1,y=bottom,y2=top),
                  pdf_style=NS(font_size=10),layout_label=label,pdf_paragraph_composition=[text])
    body = para('Some light is affected by microlen', 40,280,300,400)
    tail2=para('ng-',288.3,300,300,307)
    tail1=para('si',280.4,288,302,307,'fallback_line')
    following=para('The next line is separate.',40,280,280,299)
    result=merge_edge_fragments([body,tail2,tail1,following])
    assert result == [body,following] and body.unicode.endswith('microlensing-')
    assert body.box.x2 == 280 and body.pdf_paragraph_composition[-2:] == ['si','ng-']
    unrelated=para('extra',281,290,320,328,'fallback_line')
    assert merge_edge_fragments([body,unrelated]) == [body,unrelated]
    edited=para('Some light is affected by microlen',40,280,300,400)
    assert len(merge_edge_fragments([edited,tail1],{edited.unicode})) == 2


def test_collapsed_possessives_and_punctuated_abbreviation_residues_are_audited():
    from paperbridge.glossary import normalize_line_hyphens
    from paperbridge.translation_audit import audit_translation
    assert normalize_line_hyphens('Funded by the Union’sHorizon programme.', {}) == 'Funded by the Union’s Horizon programme.'
    assert any(i['code']=='possessive_suffix' for i in audit_translation('Funded by the Union’sHorizon programme.', '由欧盟Union’sHorizon项目资助。'))
    assert any(i['code']=='abbreviation_fragment' for i in audit_translation('For example, e.g. studies.', '例如.g.研究。'))
    assert not audit_translation('The sample has 5 g of matter.', '样品含5 g物质。')


def test_list_bullet_is_owned_by_renderer_and_country_abbreviation_is_not_seconds(monkeypatch):
    from paperbridge.translator import LocalTranslator, protect, restore
    engine=LocalTranslator();monkeypatch.setattr(engine,'load',lambda:None)
    seen=[]
    def generate(messages,budget):
        seen.append(messages[-1]['content']);return '我们测量了源的质量。'
    monkeypatch.setattr(engine,'_generate',generate)
    value,notes=engine.translate('{v1}We measured the source mass.', '', '通用科研', {}, False, {'{v1}':'•'})
    assert value=='{v1} 我们测量了源的质量。' and len(seen)==1
    assert '{v1}' not in seen[0]
    protected,tokens=protect('Funded by the U.S. Department and the U.K. Council.')
    assert 'S' not in tokens.values() and '美国' in tokens.values() and '英国' in tokens.values()
    assert restore(protected,tokens)=='Funded by the 美国 Department and the 英国 Council.'


def test_whole_paragraph_retry_receives_exact_failure_feedback(monkeypatch):
    import json,re
    from paperbridge.translator import LocalTranslator
    engine=LocalTranslator();monkeypatch.setattr(engine,'load',lambda:None);seen=[]
    def generate(messages,budget):
        content=messages[-1]['content'];seen.append(content)
        tags=list(dict.fromkeys(re.findall(r'<PB\d+>',content.split('上一稿')[0])))
        if len(seen)==1:return '样品包含'+tags[0]+tags[0]+'物体。'
        assert '失败原因' in content and '上一稿标记次数' in content and '必须各保留一次' in content
        return '样品包含'+tags[0]+'物体。'
    monkeypatch.setattr(engine,'_generate',generate)
    value,_=engine.translate('The sample contains 12 objects.', '', '通用科研', {}, False)
    assert value=='样品包含12物体。' and len(seen)==2


def test_retry_explains_missing_comparison_condition_without_relaxing_check(monkeypatch):
    import re
    from paperbridge.translator import LocalTranslator
    engine=LocalTranslator();monkeypatch.setattr(engine,'load',lambda:None);seen=[]
    def generate(messages,budget):
        content=messages[-1]['content'];seen.append(content)
        tag=re.search(r'<PB\d+>',content)[0]
        if len(seen)==1:return '该信号比参考信号强'+tag+'。'
        assert 'more than/greater than' in content and '比较差值' in content
        return '该信号比参考信号强的差值超过'+tag+'。'
    monkeypatch.setattr(engine,'_generate',generate)
    value,_=engine.translate('This signal is more than 0.4 stronger than the reference signal.', '', '通用科研', {}, False)
    assert '超过0.4' in value and len(seen)==2


def test_dust_torus_context_does_not_override_geometry_accretion_or_user_terms():
    from paperbridge.glossary import contextual_glossary
    assert contextual_glossary('An AGN dust torus emits in the infrared.', {}, 'astronomy')['torus']=='尘埃环'
    assert 'torus' not in contextual_glossary('The geometrical torus has constant curvature.', {}, 'astronomy')
    assert 'torus' not in contextual_glossary('An AGN contains dust and an accretion torus.', {}, 'astronomy')
    assert contextual_glossary('An AGN dust torus emits radiation.', {'torus':'用户环面'}, 'astronomy')['torus']=='用户环面'


def test_photometric_comparison_requires_brightness_direction():
    from paperbridge.translation_audit import audit_translation
    source='Its magnitude is more than 0.4 mag brighter than the reference magnitude.'
    assert any(i['code']=='comparison_direction' for i in audit_translation(source,'其星等超过0.4 mag于参考星等。'))
    assert not audit_translation(source,'其星等比参考星等亮的幅度超过0.4 mag。')
    assert not audit_translation(source,'其星等低于参考星等减去0.4 mag。')


def test_trailing_citation_ownership_excludes_science_and_inline_citations():
    from paperbridge.translator import detach_trailing_citation
    tokens={'<PB0>':'Smith et al., 2018','<PB1>':'Jones (2021)','<PB2>':'12'}
    assert detach_trailing_citation('The measured emission remains steady (<PB0>; <PB1>).',tokens)==('The measured emission remains steady','(<PB0>; <PB1>).')
    for text in ['The value is positive (<PB2>).','The method follows <PB0> throughout.','The signal is stable (<PB0>; measured in the source frame).']:
        assert detach_trailing_citation(text,tokens)==(text,'')


def test_sentence_recovery_owns_tail_citation_before_fresh_body_generation(monkeypatch):
    import json,re
    from paperbridge.translator import LocalTranslator,TranslationError
    engine=LocalTranslator();monkeypatch.setattr(engine,'load',lambda:None)
    seen=[]
    def generate(messages,budget):
        text=messages[-1]['content'];source=next(json.loads(x)['SOURCE'] for x in text.split('\n') if x.startswith('{') and 'SOURCE' in json.loads(x));seen.append(source)
        if 'Measurements' in source and 'This contrasts' in source:raise TranslationError('force sentence recovery')
        if source.startswith('This contrasts'):
            assert '(' not in source  # Citation absent before the model is called.
            tag=re.search(r'<PB\d+>',source)[0]
            return '这与'+tag+'中仅出现宽发射线的结果形成对比。'
        return '在整个观测过程中，测量结果保持稳定。'
    monkeypatch.setattr(engine,'_generate',generate)
    source='This contrasts with the results for Q1234 where only broad emission is found (Smith et al., 2018). Measurements remain stable throughout the full duration of the experiment.'
    value,_=engine.translate(source,'','通用科研',{},False)
    assert value.count('Q1234')==1 and value.count('Smith et al., 2018')==1 and len(seen)==4


def test_small_font_numbered_notes_can_be_plain_text_without_treating_body_as_notes():
    from paperbridge.layout_policy import is_natural_footnote,dominant_body_font
    from types import SimpleNamespace as NS
    text='1 Conventionally, this measured quantity follows the independent observations in this study.'
    assert is_natural_footnote(text,[310,680,565,735],'plain text',792,font_size=8,body_font_size=10)
    assert not is_natural_footnote(text,[310,680,565,735],'plain text',792,font_size=10,body_font_size=10)
    assert not is_natural_footnote(text,[310,100,565,150],'plain text',792,font_size=8,body_font_size=10)
    assert not is_natural_footnote('1.5 M solar mass',[310,680,565,735],'plain text',792,font_size=8,body_font_size=10)
    def p(size,count):return NS(layout_label='plain text',unicode='measurement '*count,pdf_style=NS(font_size=size))
    assert dominant_body_font([p(10,200),p(8,30),p(8,40)])==10


def test_unlabelled_small_footer_prose_can_continue_a_note_in_another_column():
    from paperbridge.layout_policy import is_natural_footnote
    text='purposes, the source may occupy only part of this area. 10 A pixel is a finite area that collects the incoming rays.'
    box=[300,670,540,754]
    assert is_natural_footnote(text,box,'abandon',842,font_size=8.4,body_font_size=10)
    assert not is_natural_footnote(text,box,'abandon',842,font_size=10,body_font_size=10)
    assert not is_natural_footnote(text,box,'figure',842,font_size=8,body_font_size=10)
    assert not is_natural_footnote('Copyright 2025. All rights reserved. This article may only be reproduced with permission.',box,'abandon',842,font_size=8,body_font_size=10)
    assert not is_natural_footnote('Department of Physics, University of Example, Main Street, 10027, City, Country',box,'abandon',842,font_size=8,body_font_size=10)


def test_single_formula_tag_is_checked_as_marker_when_source_word_spacing_is_missing():
    from paperbridge.translation_audit import audit_translation
    assert not audit_translation('The signal is observed forQ{v1} and R{v2}.','信号在Q {v1}和R{v2}中观测到。')
    assert any(i['code']=='markers' for i in audit_translation('The signal is observed forQ{v1}.','观测到Q的信号。'))
    assert any(i['code']=='math_order' for i in audit_translation('The expression is A{v1}+B{v2}.','表达式为A+B{v1}{v2}。'))


def test_digit_leading_identifiers_leave_no_unprotected_source_digits():
    import re
    from paperbridge.translator import protect,restore
    source='Contract DE-AC02- 76SF00515 and target 2MASSJ123456 are recorded at 12.5 keV.'
    masked,tokens=protect(source)
    assert '76SF00515' in tokens.values() and '2MASSJ123456' in tokens.values()
    assert not re.search(r'\d',re.sub(r'<PB\d+>','',masked))
    assert restore(masked,tokens)==source


def test_model_sees_spacing_after_formula_without_changing_saved_source(monkeypatch):
    import json,re
    from paperbridge.translator import LocalTranslator
    engine=LocalTranslator();monkeypatch.setattr(engine,'load',lambda:None)
    source='The parameter c{v1}calculated from Smith (2020) is retained.'
    def generate(messages,budget):
        content=messages[-1]['content'];line=next(x for x in content.split('\n') if x.startswith('{') and 'SOURCE' in json.loads(x))
        text=json.loads(line)['SOURCE'];assert re.search(r'<PB\d+> calculated',text)
        tags=re.findall(r'<PB\d+>',text);return '保留由'+tags[1]+'计算得到的参数'+tags[0]+'。'
    monkeypatch.setattr(engine,'_generate',generate)
    translated,_=engine.translate(source,'','通用科研',{},False,{'{v1}':'IA'})
    assert '{v1}' in translated and 'Smith (2020)' in translated
