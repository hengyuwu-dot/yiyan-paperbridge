"""Portable warnings for scientific prose, independent of paper names or IDs.

These are discrepancy detectors, not a semantic accuracy score. Warnings can
be false positives; absence of warnings does not prove semantic accuracy.
"""
import re
from collections import Counter

from .glossary import matched_terms, normalize_line_hyphens


def negation_missing(source, translation):
    """Detect a possible lost negative without treating 非常 as a negative."""
    return (bool(re.search(r"\b(?:cannot|not|without|neither)\b", source, re.I))
            and not re.search(r"不|未|无|缺|免|难|而非|并非", translation))


def english_residues(source, translation):
    """Exclude preserved scientific literals from lower-case prose warnings."""
    from .translator import protect
    import re
    # PDF mixed fonts can separate a variable from its Roman subscript.
    # Suppress only known labels attached to a formula in the English source.
    labels = r"model|obs|halo|clustered|smooth|sub|host|macro|ext|eff|los|xy|xyz"
    for match in re.finditer(r"(\{v\d+\})(" + labels + r")(?![A-Za-z])", source):
        clean_source_pattern = re.escape(match[1]) + r"\s*" + re.escape(match[2]) + r"(?![A-Za-z])"
        translation = re.sub(clean_source_pattern, match[1], translation)
    for function in ['log', 'ln', 'sin', 'cos', 'tan', 'exp']:
        # An unbracketed single-letter argument is common in d ln D/d ln a.
        # Match that argument in both texts; "log data" remains ordinary prose.
        argument = r'(?:\{v\d+\}|[_(]|\d|[A-Za-zα-ωΑ-Ω](?![A-Za-z]))'
        pattern = r'(?<![A-Za-z])' + function + r'\s*(?P<argument>' + argument + ')'
        for match in re.finditer(pattern, source):
            boundary = r'(?![A-Za-z])' if re.fullmatch(r'[A-Za-zα-ωΑ-Ω]', match['argument']) else ''
            same_argument = r'(?<![A-Za-z])' + function + r'(?=\s*' + re.escape(match['argument']) + boundary + ')'
            translation = re.sub(same_argument, '', translation)
    clean, _ = protect(translation)
    clean = re.sub(r"<PB\d+>|https?://\S+|</?b\d+>", " ", clean)
    # A retained nickname immediately after its Chinese description is useful.
    for alias in re.findall(r"\(([a-z][a-z-]{1,30})\)", source):
        clean = re.sub(r"(?<=[\u3400-\u9fff])[（(]\s*" + re.escape(alias) + r"\s*[）)]", "", clean)
    # Widely used software identifiers retain their official names.
    software = {"numpy", "scipy", "pandas", "matplotlib", "astropy", "lenstronomy", "pytorch", "tensorflow", "emcee", "dynesty"}
    allowed = {"et", "al", "doi", "arxiv", "cosmo"} | {name for name in software if re.search(r"(?<!\w)" + name + r"(?!\w)", source, re.I)}
    # Keep explicit manuscript placeholders and conventional unit symbols.
    allowed.update(re.findall(r'\b[xX]{2,}\b', source))
    if re.search(r'(?<![A-Za-z])erg(?![A-Za-z])', source):
        allowed.add('erg')
    if re.search(r'\bday\s*(?:\{v\d+\}|[-−^]\s*\d)', source):
        allowed.add('day')
    words = re.findall(r"(?<![A-Za-zÀ-ÖØ-öø-ÿ0-9_’'-])[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ’'-]*(?![A-Za-zÀ-ÖØ-öø-ÿ0-9_’'-])", clean)
    return list(dict.fromkeys(word for word in words if len(word) >= 2 and word.isascii() and word.islower() and word not in allowed))


def geometric_scale_relations(source, tokens=None):
    """Expose explicit geometric reference cases without inferring dimensions.

    The mass after 'for' is a reference condition for the aperture/radius,
    rather than an amount to add. These hints also drive discrepancy checks.
    """
    mass_expression = r'\{v\d+\}\s*M\s*\{v\d+\}'
    reference = r'<PB\d+>' if tokens is not None else mass_expression
    pattern = (r'\b(?P<property>aperture|radius|width|length|volume|area)\s+of\s+'
               r'(?P<value>(?:[^.;]|\.(?=\d)){1,60}?)\s+for\s+'
               r'(?P<reference>' + reference + r')')
    return [{"尺度名词": m['property'], "基准尺度": m['value'],
             "基准质量条件": m['reference'],
             "修饰关系": "for后的质量限定该几何尺度的基准情形，应明确写成当该质量取基准值时、孔径或尺度取给定值；不是添加的质量或数量。缩放及下限仍限定该尺度。未写radius或diameter时不要补写半径或直径。"}
            for m in re.finditer(pattern, source, re.I)
            if tokens is None or re.fullmatch(mass_expression, tokens.get(m['reference'], ''))]


def audit_translation(source, translation, glossary=None):
    from .translator import CITATION, MATH_RUN
    issues = []

    def add(code, message):
        issues.append({"code": code, "message": message})

    if not translation or not re.search(r"[\u3400-\u9fff]", translation):
        add("missing_translation", "未确认完整中文译文")
        return issues
    from .terminology import calendar_terms
    for date in calendar_terms(source).values():
        if date not in re.sub(r'\s+', '', translation):
            add("date_alignment", "英文日期的年月日或起止范围未确认，请核对：" + date)
    markers = r"\{v\d+\}|</?b\d+>|<PB\d+>"
    if Counter(re.findall(markers, source)) != Counter(re.findall(markers, translation)):
        add("markers", "公式或格式标记的数量与原文不一致")
    # A multiset of individual numbers/markers cannot detect reordered pieces
    # of one expression. Compare each adjacent, mixed-font mathematical run.
    source_runs = Counter(re.sub(r"[ \t]+", "", run) for run in re.findall(MATH_RUN, source))
    translated_runs = Counter(re.sub(r"[ \t]+", "", run) for run in re.findall(MATH_RUN, translation))
    # A single tag has no adjacent components whose order can be compared.
    # Its count is checked above. PDF word joins can make a source identifier
    # invisible to the run parser while a correctly spaced translation exposes
    # it (e.g. a preposition touching a variable). Do not reject that spacing.
    source_runs = Counter({run: count for run, count in source_runs.items() if not re.fullmatch(r"\{v\d+\}", run)})
    changed = source_runs - translated_runs
    if changed:
        add("math_order", "相邻公式片段的顺序或连接发生变化：" + "、".join(changed)[:160])
    for match in re.finditer(r"(?<!\w)(\d+(?:\.\d+)?)\s*(?:per\s+cent|percent)\b", source, re.I):
        number = match[1]
        if re.search(re.escape(number) + r"\s*(?:百分之一|分之一)", translation):
            add("percentage", "百分比可能被误写成分数")
            break
    if re.search(r"\b(?:related to|associated with|depends on)\b", source, re.I) and not re.search(r"proportional|proportionately", source, re.I) and re.search(r"成正比|成反比|正比例|反比例", translation):
        add("relation", "原文仅说明关联或依赖，译文可能加强为比例关系")
    if re.search(r"\b(?:mag|magnitudes?)\b", source, re.I):
        for word, accepted in [("brighter", r"亮|光度.{0,5}(?:高|大)|星等.{0,8}(?:小于|低于|更低|更小)"), ("fainter", r"暗|光度.{0,5}(?:低|小)|星等.{0,8}(?:大于|高于|更高|更大)")]:
            if re.search(r"\b" + word + r"\s+than\b", source, re.I) and not re.search(accepted, translation):
                add("comparison_direction", "星等比较可能遗漏更亮或更暗的方向，单独保留超过或小于不足以表达原意")
    if re.search(r"[μµ]m\b", source) and re.search(r"[μµ]\s*微米|[μµ]m\s*微米", translation):
        add("unit", "微米单位可能被拆开或重复翻译")
    if not re.search(r"\bunits?\b", source, re.I) and re.search(r"单位(?:为|是|取|：|:)\s*(?:[+-]?\d|\{v\d+\})", translation):
        add("value_as_unit", "译文可能把测量值或拟合值写成了单位，请对照原文")
    if re.search(r"\blensed\s+(?:SNe|SN|supernovae?|quasars?|stars?)\b", source, re.I) and re.search(r"透镜(?:效应|作用)?.{0,4}产生(?:了|的)?(?:超新星|类星体|恒星)", translation):
        add("lens_source_causality", "透镜作用产生的是像，译文可能误写成产生了天体本身")
    for baseline in geometric_scale_relations(source):
        mass = re.escape(baseline['基准质量条件'])
        if re.search(r'在\s*' + mass + r'\s*的\s*(?:离散)?红移(?:步长|间隔)', translation):
            add("condition_attachment", "孔径或尺度的质量基准被写成红移步长，条件修饰对象发生变化")
        elif re.search(r'(?:添加|加入|增加)\s*' + mass, translation):
            add("condition_attachment", "几何尺度的基准质量被写成直接添加的对象，请保留for的条件关系")
        elif re.search(r'在\s*' + mass + r'\s*的\s*(?:\d|\{v\d+\})', translation):
            add("condition_attachment", "基准质量与尺度直接堆叠为定语，请明确表达当质量取基准值时、尺度取给定值")
        if re.search(r'\bscaling\s+with\s+(?:the\s+)?(?:square\s+root|root)\b', source, re.I) and re.search(r'数量[^。；，]{0,12}(?:随|按)[^。；，]{0,30}平方根', translation):
            add("condition_attachment", "几何尺度的平方根缩放可能被写成数量缩放")
        if baseline['尺度名词'].casefold() == 'aperture' and not re.search(r'\b(?:radius|diameter)\b', source, re.I) and re.search(r'(?:直径|半径)为', translation):
            add("condition_attachment", "原文只写孔径，译文额外指定了半径或直径")
        root = re.search(r'\bscaling\s+with\s+(?:the\s+)?(?:square\s+root|root)(?:\s+of)?\s+(\{v\d+\}(?:[A-Za-z]+)?)', source, re.I)
        if root and not re.search(re.escape(root[1]) + r'\s*(?:的)?\s*平方根|平方根\s*[（(]?\s*' + re.escape(root[1]), translation):
            add("condition_attachment", "平方根对应的物理量未确认，不能把基准质量替换为缩放变量")
    terms = matched_terms(normalize_line_hyphens(source, glossary or {}), glossary or {})
    missing = [f"{english} → {chinese}" for english, chinese in terms.items() if chinese not in translation]
    if missing:
        add("terminology", "未确认采用词表中的译名：" + "、".join(missing)[:350])
    # Protect minimal citations, not whole parentheses containing explanations.
    clean = re.sub(CITATION + r"|https?://\S+|\{v\d+\}|</?b\d+>", "", translation)
    prose = re.findall(r"\b[a-z]{2,}(?:\s+[a-z]{2,}){3,}\b", clean)
    if prose:
        add("english_prose", "译文仍包含连续英文说明：" + "、".join(dict.fromkeys(prose))[:180])
    if re.search(r"[\u3400-\u9fff]\s*(?:us|we|our|them|their|this|that)\s*[\u3400-\u9fff]", clean):
        add("english_function_word", "中文句子中可能残留未翻译的英文代词或指示词")
    if re.search(r"(?:[\u3400-\u9fff]|\s)(?:to|from|with|between|than)(?=\d)", clean):
        add("english_joined_quantity", "中文句子中可能残留与数量粘连的英文介词")
    if re.search(r"\b(?:model|simulation)\s+realizations?\b", normalize_line_hyphens(source, glossary or {}), re.I) and "模型实现" in clean:
        add("model_realization", "模拟得到的模型实例或样本被机械译为模型实现，请核对表达")
    if re.search(r'\ba factor of\s+(?:two|three|four|five|six|seven|eight|nine|ten|\d)', source, re.I) and re.search(r'一个[两二三四五六七八九十]|[两二三四五六七八九十]的不确定性(?:因素|因子)', clean):
        add("factor_literal", "倍数短语可能被机械译成数量或因素，请核对倍数及不确定性表达")
    if re.search(r"[A-Za-z]['’]s(?:\b|(?=[A-Z]))", source) and (re.search(r"[（(]\s*s\s*[)）]", clean) or re.search(r"(?<![A-Za-z])[A-Za-z]+['’]s(?=[\u3400-\u9fffA-Z])", clean)) and not re.search(r"\bseconds?\b|(?:\d|\{v\d+\})\s*s\b|\(\s*s\s*\)", source):
        add("possessive_suffix", "英文所有格尾字母可能残留或被当作科学单位，请核对中文表达")
    if re.search(r"\be\s*\.\s*g\s*\.", source, re.I) and re.search(r"(?:例如|比如|譬如|如)\s*\.?\s*g(?=\s|[.。\u3400-\u9fff])", clean):
        add("abbreviation_fragment", "例如或如之后可能残留了英文缩写 e.g. 的尾字母")
    if not re.search(r"\b(?:paired|pairs?|binary|dual|double|both)\b", source, re.I) and re.search(r"([两二三四五六七八九十])(?:个|种|位|条|项|组|对|次)\1(?![二三四五六七八九十百千万]|角|体|元|维|重|边|面|极|方|轴)", clean):
        add("duplicate_quantity", "相邻数量词可能重复，请核对中文表达")
    if glossary is not None:
        from .terminology import counted_terms
        absent_counts = []
        for phrase in counted_terms(source, glossary).values():
            if phrase in translation:
                continue
            image_count = re.fullmatch(r'([两一二三四五六七八九十]|\d+)(?:幅|个)图像', phrase)
            if image_count and re.search(re.escape(image_count[1]) + r'(?:个像|幅图像|张图像|个图像)', translation):
                continue
            absent_counts.append(phrase)
        if absent_counts:
            add("count_alignment", "数量与对象未成组保留：" + "、".join(absent_counts))
    residues = re.findall(r"(?<![A-Za-z0-9_])(?:regime|years?|months?|because|however|therefore|where|which|these|those|between|using|without|within|such)(?![A-Za-z0-9_])", clean)
    if residues:
        add("english_common_word", "中文中可能残留普通英文词：" + "、".join(sorted(set(residues))))
    if re.search(r"[两二三四五六七八九十](?:通量比|恒星|类星体|参数|样本)(?![率度])", clean):
        add("missing_classifier", "计数名词可能缺少量词，请核对几个参数或几颗恒星等表达")
    # Narrow language warnings, never an automatic semantic accuracy score.
    labels = {"方程", "公式", "密度", "通量", "概率", "模型", "质量", "速度", "温度"}
    labels.update(value for value in (glossary or {}).values() if 2 <= len(value) <= 12)
    repeated = [word for word in labels if re.search(re.escape(word) + r"\s*" + re.escape(word), clean)]
    if repeated:
        add("repeated_term", "专业名词或方程标签可能紧邻重复：" + "、".join(sorted(repeated)))
    tangled = [word for word in set(terms.values()) if len(word) >= 2 and re.search(
        re.escape(word) + r"[^。；，]{0,40}之间[^。；，]{0,25}" + re.escape(word), clean)]
    if tangled:
        add("noun_relation", "对象之间的数量关系可能表达重复，请对照原文：" + "、".join(sorted(tangled)))
    return issues
