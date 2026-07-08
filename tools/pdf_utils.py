from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MYANMAR_FONT_NAME = "MyanmarFont"
ENGLISH_FONT_NAME = "Helvetica"
MYANMAR_FONT_PATH = PROJECT_ROOT / "fonts" / "NotoSansMyanmar-Regular.ttf"
MYANMAR_FONT_MISSING_MESSAGE = "Myanmar font file missing. Please add fonts/NotoSansMyanmar-Regular.ttf"

_MYANMAR_FONT_REGISTERED = False


def contains_myanmar(text):
    if text is None:
        return False
    text = str(text)
    return any("\u1000" <= ch <= "\u109F" or "\uAA60" <= ch <= "\uAA7F" for ch in text)


def contains_myanmar_value(value):
    if isinstance(value, dict):
        return any(contains_myanmar_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(contains_myanmar_value(item) for item in value)
    return contains_myanmar(value)


def ensure_myanmar_font_registered():
    global _MYANMAR_FONT_REGISTERED
    if _MYANMAR_FONT_REGISTERED:
        return
    if not MYANMAR_FONT_PATH.exists():
        raise FileNotFoundError(MYANMAR_FONT_MISSING_MESSAGE)

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont(MYANMAR_FONT_NAME, str(MYANMAR_FONT_PATH)))
    _MYANMAR_FONT_REGISTERED = True


def font_for_text(text):
    return MYANMAR_FONT_NAME if contains_myanmar(text) else ENGLISH_FONT_NAME


def paragraph_styles():
    ensure_myanmar_font_registered()
    from reportlab.lib.styles import ParagraphStyle

    english_style = ParagraphStyle(
        "EnglishCell",
        fontName=ENGLISH_FONT_NAME,
        fontSize=8,
        leading=10,
    )
    myanmar_style = ParagraphStyle(
        "MyanmarCell",
        fontName=MYANMAR_FONT_NAME,
        fontSize=8,
        leading=12,
    )
    return english_style, myanmar_style


def make_cell(value):
    ensure_myanmar_font_registered()
    from reportlab.platypus import Paragraph

    value = "" if value is None else str(value)
    english_style, myanmar_style = paragraph_styles()
    style = myanmar_style if contains_myanmar(value) else english_style
    return Paragraph(value, style)
