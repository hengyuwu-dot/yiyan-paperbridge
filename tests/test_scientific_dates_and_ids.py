import re

from paperbridge.layout_policy import literal_reason
from paperbridge.terminology import calendar_terms
from paperbridge.translator import protect, restore


def test_catalogue_identifiers_are_not_truncated_as_author_year_citations():
    for source in ['SNe 2023abc, 2026def, and 2025xyz', 'SN 2020abcdef', 'AT 2019xyz']:
        protected, tokens = protect(source)
        assert restore(protected, tokens) == source
        for identifier in re.findall(r'[12]\d{3}[a-z]+', source):
            assert identifier in tokens.values()
    _, tokens = protect('Smith 2020a and Smith 2020b describe the sample.')
    assert 'Smith 2020a' in tokens.values()
    assert 'Smith 2020b' in tokens.values()


def test_fractional_ut_dates_keep_year_month_and_day_bound_together():
    cases = {
        '2024 December 31.48': '2024年十二月31.48日',
        'May 8, 2025': '2025年五月8日',
        'December 31.44': '十二月31.44日',
        '2020 February 29.3': '2020年二月29.3日',
    }
    for source, target in cases.items():
        assert calendar_terms(source)[source] == target
        protected, tokens = protect(source)
        assert restore(protected, tokens) == target
        assert sorted(re.findall(r'\d+(?:\.\d+)?', source)) == sorted(re.findall(r'\d+(?:\.\d+)?', target))
    assert not calendar_terms('2025 February 29.2')
    assert not calendar_terms('2025 April 31')


def test_scientific_identifiers_and_formula_table_headers_do_not_need_chinese():
    for source in ['2023xyz', '2.1.1. SN 2023xyz', 'E(B{v1}V){v2}(mag)', 'μ{v1}(mag)', 'xxx']:
        assert literal_reason(source, 'paragraph')
    assert not literal_reason('SN 2023xyz has an evolving light curve.', 'paragraph')
    assert not literal_reason('We measure a flux in erg.', 'paragraph')


def test_font_split_identifier_suffix_requires_adjacent_catalogue_prefix():
    from paperbridge.layout_policy import identifier_suffix
    box = [200, 100, 210, 107]
    assert identifier_suffix('abc', box, [('Keywords: SN 2023', [40, 97, 199, 108])])
    assert not identifier_suffix('abc', box, [('Measurements in 2023', [40, 97, 199, 108])])
    assert not identifier_suffix('abc', box, [('SN 2023', [40, 70, 199, 81])])
    assert not identifier_suffix('abc', box, [('SN 2023', [40, 97, 170, 108])])


def test_literal_audit_keeps_scientific_units_and_math_functions_but_flags_prose():
    from paperbridge.translation_audit import english_residues
    source='The rate is 0.1 mag day{v1}; luminosity is 1e42 erg s{v2}; log{v3}(d) is used.'
    assert not english_residues(source,'速率为0.1 mag day{v1}；光度为1e42 erg s{v2}，采用log{v3}(d)。')
    assert english_residues('Every day is observed.', '每个day都进行了观测。') == ['day']
    assert english_residues('The log is stored.', '保存log。') == ['log']
    assert not english_residues('Accepted xx xx, 2026', '接收日期：2026年xx xx')


def test_explicit_heading_line_breaks_keep_style_without_mutating_input():
    from babeldoc.format.pdf.document_il import PdfParagraphComposition,PdfSameStyleUnicodeCharacters,PdfStyle
    from paperbridge.layout_policy import split_unicode_lines
    style=PdfStyle(font_id='source',font_size=9)
    original=PdfParagraphComposition(pdf_same_style_unicode_characters=PdfSameStyleUnicodeCharacters(pdf_style=style,unicode='附录A：观测\n附录B：方法\n附录C：致谢'))
    lines=split_unicode_lines([original])
    assert [g[0].pdf_same_style_unicode_characters.unicode for g in lines]==['附录A：观测','附录B：方法','附录C：致谢']
    assert all(g[0].pdf_same_style_unicode_characters.pdf_style.font_id=='source' for g in lines)
    assert '\n' in original.pdf_same_style_unicode_characters.unicode
