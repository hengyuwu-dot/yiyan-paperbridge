"""Keep numeric scripts as original PDF glyphs instead of translating digits."""
import re


def has_numeric_scripts(formula):
    chars = [c for c in formula.pdf_character if c.char_unicode and not c.char_unicode.isspace()]
    if len(chars) < 2 or not re.fullmatch(r"[0-9,.+−-]+", "".join(c.char_unicode for c in chars)):
        return False
    # Font size alone also changes in ordinary typography. Require a raised
    # or lowered glyph next to a larger numeric glyph, in PDF coordinates.
    for left, right in zip(chars, chars[1:]):
        if not left.pdf_style or not right.pdf_style or not left.box or not right.box:
            continue
        small, large = sorted((left, right), key=lambda c: c.pdf_style.font_size)
        size = large.pdf_style.font_size
        if size and small.pdf_style.font_size < .9 * size and abs(small.box.y - large.box.y) > .18 * size:
            return True
    return False


def numeric_script_parser(base_class, edited_regions=(), on_protected=None):
    """Extend the pinned parser without changing BabelDOC's installed files.

    Existing user edits retain their previous placeholder scheme. Automatically
    translated text can be regenerated with the corrected formula boundaries.
    """
    class NumericScriptParser(base_class):
        def process_page(self, page):
            self._script_page = page.page_number + 1
            self._script_height = page.cropbox.box.y2
            return super().process_page(page)

        def is_translatable_formula(self, formula):
            if has_numeric_scripts(formula):
                b = formula.box
                rectangle = (b.x, self._script_height - b.y2, b.x2, self._script_height - b.y)
                edited = any(number == self._script_page and
                             box[0] - .1 <= rectangle[0] and box[1] - .1 <= rectangle[1] and
                             box[2] + .1 >= rectangle[2] and box[3] + .1 >= rectangle[3]
                             for number, box in edited_regions)
                if not edited:
                    if on_protected:
                        on_protected(self._script_page, formula)
                    return False
            return super().is_translatable_formula(formula)
    return NumericScriptParser


def readable_numeric_hint(formula):
    """Expose confirmed numeric script geometry to the translator, not the PDF.

    A flattened '108' can mean 108 or 10 to the eighth power. Only distinctly
    smaller, displaced glyphs are annotated; ordinary numbers stay untouched.
    The original glyph objects and placeholder text are never mutated.
    """
    chars = [c for c in formula.pdf_character if c.char_unicode and not c.char_unicode.isspace()]
    plain = ''.join(c.char_unicode for c in chars)
    if not has_numeric_scripts(formula):
        return plain
    sizes = [c.pdf_style.font_size for c in chars if c.pdf_style and c.box]
    if not sizes:
        return plain
    size = max(sizes)
    baselines = sorted(c.box.y for c in chars if c.pdf_style and c.box and c.pdf_style.font_size >= .9 * size)
    if not baselines:
        return plain
    baseline = baselines[len(baselines) // 2]
    groups = []
    for char in chars:
        script = ''
        if char.pdf_style and char.box and char.pdf_style.font_size < .9 * size:
            displacement = char.box.y - baseline
            if abs(displacement) > .18 * size:
                script = '^' if displacement > 0 else '_'
        if groups and groups[-1][0] == script:
            groups[-1][1] += char.char_unicode
        else:
            groups.append([script, char.char_unicode])
    return ''.join(kind + '(' + text + ')' if kind else text for kind, text in groups)
