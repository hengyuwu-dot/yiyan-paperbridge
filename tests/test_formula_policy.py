from types import SimpleNamespace as NS

from paperbridge.formula_policy import has_numeric_scripts, numeric_script_parser


def formula(exponent_y=3, exponent_size=7, text="103"):
    return NS(pdf_character=[NS(char_unicode=c, pdf_style=NS(font_size=exponent_size if i == 2 else 10),
                               box=NS(x=i * 5, y=exponent_y if i == 2 else 0))
                             for i, c in enumerate(text)],
              box=NS(x=0, y=0, x2=15, y2=12))


def test_numeric_superscripts_and_subscripts_require_geometry_not_digit_spelling():
    assert has_numeric_scripts(formula())
    assert has_numeric_scripts(formula(exponent_y=-3))
    assert not has_numeric_scripts(formula(exponent_y=0))
    assert not has_numeric_scripts(formula(exponent_size=10))
    assert not has_numeric_scripts(formula(text="AB3"))
    assert not has_numeric_scripts(formula(exponent_y=.5))


def test_negative_exponent_original_glyph_objects_are_preserved():
    f = formula(text="10−3")
    f.pdf_character[-1].pdf_style.font_size = 7
    f.pdf_character[-1].box.y = 3
    assert has_numeric_scripts(f)
    originals = list(f.pdf_character)
    class Base:
        def is_translatable_formula(self, value):
            return True
    parser = numeric_script_parser(Base)()
    parser._script_page, parser._script_height = 1, 800
    assert not parser.is_translatable_formula(f)
    assert all(a is b for a, b in zip(originals, f.pdf_character))


def test_saved_user_edits_keep_their_previous_placeholder_scheme():
    class Base:
        def is_translatable_formula(self, value):
            return True
    parser = numeric_script_parser(Base, [(1, [0, 780, 30, 800])])()
    parser._script_page, parser._script_height = 1, 800
    assert parser.is_translatable_formula(formula())
    parser._script_page = 2
    assert not parser.is_translatable_formula(formula())
    assert parser.is_translatable_formula(formula(exponent_y=0))


def test_formula_reference_distinguishes_powers_and_plain_numbers_without_changing_glyphs():
    from paperbridge.formula_policy import readable_numeric_hint
    raised = formula(text='108')
    originals = [vars(c).copy() for c in raised.pdf_character]
    assert readable_numeric_hint(raised) == '10^(8)'
    assert readable_numeric_hint(formula(text='108',exponent_y=-3)) == '10_(8)'
    assert readable_numeric_hint(formula(text='108',exponent_y=0)) == '108'
    assert [vars(c) for c in raised.pdf_character] == originals
