"""Two-page spread scans: Tesseract's layout pass said "Empty page!!" on whole spreads of a
Telugu novel and the pages were dropped from the book (AgniPravesam, ysvsr 11-18).
A weak or empty read of a landscape page is retried as left and right halves.
Run: python3 test_spread.py"""
from io import BytesIO
from PIL import Image
import app


def _png(w, h):
    out = BytesIO()
    Image.new("L", (w, h), 255).save(out, "PNG")
    return out.getvalue()


def fake_tess(png, page_w, page_h, lang="eng", conf=False):
    w, h = Image.open(BytesIO(png)).size
    if w > h:  # the whole spread: Tesseract finds nothing
        return ("", 0.0, 0.0, []) if conf else ("", 0.0)
    side = "left" if fake_tess.calls % 2 == 0 else "right"
    fake_tess.calls += 1
    text = f"{side} page words " * 10
    return (text, 0.1, 88.0, [(0.0, 0.8, 1.0, 1.0)]) if conf else (text, 0.1)


def test_empty_spread_read_as_halves():
    fake_tess.calls = 0
    real, app._tess = app._tess, fake_tess
    try:
        text, cov, pics, c = app._tess_mixed(_png(1600, 1300), 1600, 1300, "tel")
    finally:
        app._tess = real
    assert text.index("left page") < text.index("right page"), text
    assert c == 88.0
    assert pics == [(0.0, 0.8, 0.5, 1.0), (0.5, 0.8, 1.0, 1.0)], pics


def test_portrait_page_not_split():
    fake_tess.calls = 0
    real, app._tess = app._tess, fake_tess
    try:
        text, *_ = app._tess_mixed(_png(1000, 1400), 1000, 1400, "tel")
    finally:
        app._tess = real
    assert fake_tess.calls == 1 and "left page" in text


TEL_PARA = "ఆమెకు రెండు మూడుసార్లు చదివితేనేగానీ అర్ధంకాలేదు."
ENG_PARA = "For the man, an attractive girl, and for the woman an attractive man, are the prizes they are after."


def fake_mixed(png, page_w, page_h, lang="eng", conf=False):
    """An English paragraph quoted in a Telugu page: the Telugu model reads it as digits."""
    if lang == "tel":
        text = TEL_PARA + "\n\n0% (౧౭ ౧౭౫౧, 2౧ 260౮2006 క్ర1- 200౮ 10% ౮16\n\n" + TEL_PARA
        c = 82.0
    elif lang == "eng":
        text, c = "junk " * 30, 40.0
    else:  # tel+eng: English right, one Telugu word turned Latin
        text, c = TEL_PARA.replace("అర్ధంకాలేదు", "Ho") + "\n\n" + ENG_PARA + "\n\n" + TEL_PARA, 80.0
    return (text, 0.1, c, []) if conf else (text, 0.1)


def test_english_paragraph_in_telugu_page():
    """AgniPravesam p.32 quotes a letter in English (ysvsr 11-18): only that paragraph is swapped."""
    real, app._tess = app._tess, fake_mixed
    try:
        text, *_ = app._tess_mixed(_png(1000, 1400), 1000, 1400, "tel")
    finally:
        app._tess = real
    assert text.split("\n\n") == [TEL_PARA, ENG_PARA, TEL_PARA], text


if __name__ == "__main__":
    test_english_paragraph_in_telugu_page()
    test_empty_spread_read_as_halves()
    test_portrait_page_not_split()
    print("ok: spreads")
