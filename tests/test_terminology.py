import re
from collections import Counter
import json
import pytest

from fastapi.testclient import TestClient

from paperbridge.app import app
from paperbridge.glossary import matched_terms, normalize_line_hyphens, terms_for
from paperbridge.terminology import atomic_terms, terminology_entries
from paperbridge.translation_audit import audit_translation
from paperbridge.translator import LocalTranslator, TranslationError, protect, restore


def test_domain_terms_disambiguation_and_user_choice():
    terms = terms_for('astronomy', 'Flux Ratio = 用户通量比')
    assert terms['Flux Ratio'] == '用户通量比'
    assert terms['sub-solar mass'] == '亚太阳质量'
    assert terms['credible interval'] != terms['confidence interval']
    assert 'flux ratio' not in terms_for('biomed')
    assert terms['lensing galaxy'] == '透镜星系'
    assert terms['astroid caustic'] == '星形线焦散'
    assert 'asteroid' not in terms
    assert matched_terms('The lensing galaxy and its flux ratio.', terms) == {
        'lensing galaxy': '透镜星系', 'Flux Ratio': '用户通量比'}


def test_noun_binding_preserves_formula_values_and_never_pins_arbitrary_verbs():
    source = 'Flux ratios constrain sub-solar mass black holes at {v1} with 95% confidence (Smith 2020).'
    terms = terms_for('astronomy', 'constrain = 限制\nFlux ratios = 用户通量比')
    bound = atomic_terms(source, terms)
    assert bound['Flux ratios'] == '用户通量比'
    assert 'constrain' not in bound
    protected, tokens = protect(source, bound)
    restored = restore(protected, tokens)
    assert '用户通量比' in restored and '亚太阳质量' in restored
    assert '{v1}' in restored and 'Smith 2020' in restored
    assert Counter(re.findall(r'\d+', source)) == Counter(re.findall(r'\d+', restored))


def test_attached_formula_labels_are_preserved_without_hiding_separated_prose():
    source = 'We compare {v1}model and {v2}obs for {v3}halo and {v4}clustered in the model halo.'
    protected, tokens = protect(source)
    assert restore(protected, tokens) == source
    assert {'{v1}model', '{v2}obs', '{v3}halo', '{v4}clustered'} <= set(tokens.values())
    assert 'in the model halo.' in protected


def test_pdf_word_joins_repaired_without_rewriting_identifiers_or_unknown_words():
    source = 'Weapply ourmethod to11 quadruply-imaged quasars and use fluxratios for TOI11 and GW170817.'
    cleaned = normalize_line_hyphens(source, terms_for('astronomy'))
    assert 'We apply our method to 11' in cleaned and 'flux ratios' in cleaned
    assert 'TOI11' in cleaned and 'GW170817' in cleaned
    assert normalize_line_hyphens('Theunmatchedword remains.', {}) == 'Theunmatchedword remains.'
    assert normalize_line_hyphens('A power- law slope is measured.', terms_for('general')) == 'A power-law slope is measured.'


def test_language_audit_separates_residues_from_correct_scientific_prose():
    terms = terms_for('astronomy')
    assert {'terminology', 'english_joined_quantity'} <= {i['code'] for i in audit_translation(
        'We apply the method to11 quasars and measure flux ratios.', '我们将方法用于to11个类星体并测量流量比。', terms)}
    assert not audit_translation('We use the model realizations.', '我们采用这些模型样本。')
    assert any(i['code'] == 'model_realization' for i in audit_translation('We use the model realizations.', '我们采用模型实现。'))


def test_searchable_pack_metadata_and_sources_served_without_model_or_network():
    entries = terminology_entries('astronomy')
    assert any(e['english'] == 'flux ratio' and e['sources'] and e['note'] for e in entries)
    assert all(s['url'].startswith('https://') for e in entries for s in e['sources'])
    with TestClient(app) as client:
        result = client.get('/api/terminology/astronomy').json()
        assert result['entries'] == entries
        assert client.get('/api/terminology/unknown').status_code == 400
        assert client.get('/api/glossary/astronomy').json()['flux ratio'] == '通量比'


def test_visible_noun_retry_keeps_quantitative_protection(monkeypatch):
    translator = LocalTranslator()
    translator.model = object()
    monkeypatch.setattr(translator, 'load', lambda: None)
    calls = []

    def generate(messages, budget):
        content = messages[-1]['content']
        source = json.JSONDecoder().raw_decode(content[content.index('{'):])[0]['SOURCE']
        tokens = re.findall(r'<PB\d+>', source)
        calls.append(tokens)
        if len(tokens) > 1:
            return '测量' + ''.join(tokens) + tokens[0]
        return '通量比约束' + tokens[0] + '的置信限。'

    monkeypatch.setattr(translator, '_generate', generate)
    value, notes = translator.translate('Flux ratios constrain 95% confidence limits.', '', '天文与物理', terms_for('astronomy'), polish=False)
    assert value == '通量比约束95%的置信限。'
    assert [len(tokens) for tokens in calls] == [2, 2, 1]
    assert any('可见词表复译' in note for note in notes)

    monkeypatch.setattr(translator, '_generate', lambda messages, budget: '通量比约束96%的置信限。')
    with pytest.raises(TranslationError):
        translator.translate('Flux ratios constrain 95% confidence limits.', '', '天文与物理', terms_for('astronomy'), polish=False)


def test_model_load_failure_never_triggers_noun_retry(monkeypatch):
    translator = LocalTranslator()
    calls = []

    def fail_load():
        calls.append('load')
        raise TranslationError('本地模型加载失败')

    monkeypatch.setattr(translator, 'load', fail_load)
    with pytest.raises(TranslationError, match='本地模型加载失败'):
        translator.translate('Flux ratios constrain 95% confidence limits.', '', '天文与物理', terms_for('astronomy'))
    assert calls == ['load']

def test_repeated_equation_names_and_tangled_relationships_are_soft_warnings():
    assert any(i['code'] == 'repeated_term' for i in audit_translation(
        'Using the microlensing equation Eq. 15.', '使用微引力透镜方程方程15。'))
    terms = terms_for('astronomy')
    assert any(i['code'] == 'noun_relation' for i in audit_translation(
        'Three flux ratios between four images.', '得到三种通量比之间的四个像的通量比。', terms))
    assert not audit_translation('Three flux ratios between four images.', '得到四个像之间的三个通量比。', terms)
    assert not audit_translation('Equation 15 and equation 16.', '式15与式16。')


def test_long_sentences_keep_nouns_visible_and_do_not_repeat_an_identical_failed_retry(monkeypatch):
    translator = LocalTranslator(); translator.model = object()
    monkeypatch.setattr(translator,'load',lambda:None)
    source = ('Flux ratios are measured for the images in the scientific model, ' * 5) + 'with 95% confidence.'
    calls = []
    def failed(messages,budget):
        payload = messages[-1]['content']
        protected = json.JSONDecoder().raw_decode(payload[payload.index('{'):])[0]['SOURCE']
        assert 'Flux ratios' in protected
        calls.append(protected)
        return '通量比测量，没有保留数量。'
    monkeypatch.setattr(translator,'_generate',failed)
    with pytest.raises(TranslationError):
        translator.translate(source,'','天文与物理',terms_for('astronomy'),polish=False)
    assert len(calls) == 2


def test_optical_regimes_translate_as_physical_domains_and_common_english_residue_is_visible():
    terms = terms_for('astronomy')
    source = normalize_line_hyphens('The wave-opticsregime differs from the geometric-optics regime.',terms)
    assert 'wave-optics regime' in source
    assert terms['wave-optics regime'] == '波动光学区'
    assert 'regime' not in terms_for('biomed')
    assert any(i['code'] == 'english_common_word' for i in audit_translation('The geometric-optics regime.', '几何光学 regime。',terms))
    assert not any(i['code'] == 'english_common_word' for i in audit_translation('The model uses REGIME as its name.', '模型名为REGIME。'))


def test_duration_compounds_are_not_confused_with_scientific_identifiers():
    source='A 10-year survey with a 0.5-hour exposure observes TOI11 and GW170817.'
    protected,tokens=protect(source)
    value=restore(protected,tokens)
    assert '10年' in value and '0.5小时' in value
    assert 'TOI11' in value and 'GW170817' in value
    assert Counter(re.findall(r'\d+(?:\.\d+)?',source)) == Counter(re.findall(r'\d+(?:\.\d+)?',value))
    assert terms_for('astronomy')['lt-days'] == '光日'


def test_mass_baselines_do_not_become_redshift_steps_and_simulation_verbs_are_contextual():
    from paperbridge.glossary import contextual_glossary
    source='We use discrete redshift steps within an aperture of 0.24" for {v1}M{v2}, scaling with the square root of mass.'
    wrong='我们在{v1}M{v2}的离散红移步长上使用0.24"的孔径。'
    right='我们沿离散红移步长加入对象；对于{v1}M{v2}，孔径为0.24"，并随质量平方根缩放。'
    assert any(i['code']=='condition_attachment' for i in audit_translation(source,wrong))
    assert not any(i['code']=='condition_attachment' for i in audit_translation(source,right))
    context='We render a population of haloes and subtract the total mass.'
    terms=terms_for('astronomy')
    assert contextual_glossary(context,terms,'astronomy')['render']=='生成'
    assert 'render' not in contextual_glossary('We render a halo for graphics display.',terms,'astronomy')
    assert contextual_glossary(context,{**terms,'render':'用户译名'},'astronomy')['render']=='用户译名'


def test_counts_stay_attached_to_objects_and_do_not_force_units_into_countable_nouns():
    from paperbridge.terminology import counted_terms
    from paperbridge.glossary import contextual_glossary
    source='We obtain three flux ratios between four images in the lens system.'
    terms=contextual_glossary(source,terms_for('astronomy'),'astronomy')
    counts=counted_terms(source,terms)
    assert counts=={'three flux ratios':'三个通量比','four images':'四个像'}
    protected,tokens=protect(source,counts=counts)
    restored=restore(protected,tokens)
    assert '三个通量比' in restored and '四个像' in restored
    assert any(i['code']=='count_alignment' for i in audit_translation(source,'三个像之间的通量比四。',terms))
    assert not any(i['code']=='count_alignment' for i in audit_translation(source,'四个像之间的三个通量比。',terms))
    assert counted_terms('We use 4 samples, two parameters, and three solar masses.',terms_for('general'))=={'4 samples':'4个样本','two parameters':'两个参数'}
    from paperbridge.translator import SYSTEM
    assert '<PB数字>' not in SYSTEM


def test_count_binding_owns_complete_nouns_and_not_modifiers():
    from paperbridge.terminology import counted_terms
    assert counted_terms('We compare four model parameters and two samples.',{}) == {'four model parameters':'四个模型参数','two samples':'两个样本'}
    assert counted_terms('We compare four image samples.',{}) == {}
    assert counted_terms('We compare two model variants.',{}) == {}
    assert counted_terms('2.2 Model parameters',{}) == {}
    assert counted_terms('The measurement is 1.2 samples.',{}) == {}


def test_geometric_reference_cases_keep_their_objects_and_do_not_invent_diameters():
    from paperbridge.translation_audit import geometric_scale_relations
    source='We add PBH within a circular aperture of 0.24" for {v1}M{v2}, scaling with the root {v3}PBH to a minimum of 0.15".'
    assert geometric_scale_relations(source)[0]['基准质量条件']=='{v1}M{v2}'
    protected,tokens=protect(source.replace('circular aperture','aperture'))
    relation=geometric_scale_relations(protected,tokens)[0]
    assert tokens[relation['基准质量条件']]=='{v1}M{v2}'
    assert '<PB' in relation['基准尺度']
    wrong=[
        '我们在0.24"的孔径内添加{v1}M{v2}，按{v3}PBH平方根缩放，最低0.15"。',
        '对于{v1}M{v2}，孔径为0.24"；其数量随{v3}PBH的平方根缩放，最低0.15"。',
        '对于{v1}M{v2}，直径为0.24"的圆形孔径随{v3}PBH的平方根缩放，最低0.15"。',
        '我们在{v1}M{v2}的0.24"圆形孔径内加入PBH，按{v3}PBH平方根缩放，最小0.15"。',
    ]
    for value in wrong:
        assert any(i['code']=='condition_attachment' for i in audit_translation(source,value))
    right='我们在圆形孔径内加入PBH。对于{v1}M{v2}，孔径为0.24"，随{v3}PBH的平方根缩放，最小为0.15"。'
    assert not any(i['code']=='condition_attachment' for i in audit_translation(source,right))
    swapped='我们在0.24"圆形孔径内加入{v3}PBH，尺度随{v1}M{v2}的平方根缩放，最小0.15"。'
    assert any(i['code']=='condition_attachment' for i in audit_translation(source,swapped))
    protected,tokens=protect(source)
    assert any('以{v1}M{v2}为质量基准、孔径为0.24"的圆形区域' == value for value in tokens.values())
    restored=restore(protected,tokens)
    assert Counter(re.findall(r'\{v\d+\}',restored))==Counter(re.findall(r'\{v\d+\}',source))


def test_fully_bound_counted_caption_needs_no_model_generation(monkeypatch):
    translator=LocalTranslator()
    monkeypatch.setattr(translator,'load',lambda: (_ for _ in ()).throw(AssertionError('fixed phrase should not load model')))
    value,notes=translator.translate('Three parameters.','','通用科研',terms_for('general'))
    assert value=='三个参数。' or value=='三个参数.'
    assert notes


def test_joined_calendar_dates_preserve_day_ranges_and_all_original_digits():
    from paperbridge.terminology import calendar_terms
    source='The workshop was held between 18-22 of July2022 and on 3rd March 2024.'
    expected={'18-22 of July2022':'2022年七月18日至22日','3rd March 2024':'2024年三月3日'}
    assert calendar_terms(source)==expected
    protected,tokens=protect(source)
    restored=restore(protected,tokens)
    assert all(value in restored for value in expected.values())
    assert Counter(re.findall(r'\d+',restored))==Counter(re.findall(r'\d+',source))
    assert calendar_terms('31 February 2024; 22-18 July2022; Target18July2022')=={}
    assert any(i['code']=='date_alignment' for i in audit_translation(source,'研讨会在July2022年18月至22月和2024年三月3日举行。'))
    assert not any(i['code']=='date_alignment' for i in audit_translation(source,'研讨会于2022年七月18日至22日及2024年三月3日举行。'))


def test_multiplicative_uncertainty_is_not_a_countable_factor():
    source='The unknown masses render the results uncertain by a factor of two.'
    protected,tokens=protect(source)
    assert '具有两倍的不确定性' in tokens.values()
    assert 'a factor of' not in protected
    assert any(i['code']=='factor_literal' for i in audit_translation(source,'结果存在一个两的不确定性因素。'))
    assert not audit_translation(source,'未知质量使结果具有两倍的不确定性。')
