"""Regression suite: one sample PDF per kind of file people upload, run through the same
pipeline the site uses, checked two ways:

  1. Rules written by hand (path, phrases that must or must not appear, pictures kept).
     These say what correct means and never change by accident.
  2. A snapshot in tests/golden.json (chapter count, headings, paragraphs, pictures, words).
     Any drift fails, so a fix for one kind of file can't quietly change another.

Run:      python3 test_regression.py
Accept:   python3 test_regression.py --update   (after a change you meant; review the diff)
Add a kind: write a make_* function, add it to CASES with its rules, run --update.
"""
import json, sys
from pathlib import Path

import pymupdf
from app import _text_blocks, _structure, ocr_doc, ocr_chapters, _scan_figures, ocr_ok, ocr_lang, pdf_toc, doc_lang

GOLDEN = Path(__file__).parent / "tests" / "golden.json"
PROSE = ("It was a bright cold day in April, and the clocks were striking thirteen. "
         "Winston Smith slipped quickly through the glass doors of Victory Mansions. ")


def _page_png(text, color=False, dpi=150):
    p = pymupdf.open().new_page()
    if color:  # comic panel: coloured shapes plus a speech bubble
        p.draw_rect(pymupdf.Rect(40, 40, 555, 400), fill=(0.9, 0.5, 0.2))
        p.draw_circle((300, 600), 150, fill=(0.2, 0.4, 0.8))
        p.draw_oval(pymupdf.Rect(80, 420, 330, 520), fill=(1, 1, 1), color=(0, 0, 0))
        p.insert_textbox(pymupdf.Rect(95, 440, 320, 510), text, fontsize=14)
    else:
        p.insert_textbox(pymupdf.Rect(72, 72, 520, 760), text, fontsize=12)
    return p.get_pixmap(dpi=dpi).tobytes("png")


def _doc():
    return pymupdf.open()


def make_novel():
    """Born-digital book: chapter titles, running header, page numbers."""
    d = _doc()
    for ch in (1, 2):
        for k in range(3):
            pg = d.new_page()
            pg.insert_text((200, 40), "NINETEEN EIGHTY-FOUR", fontsize=8)
            pg.insert_text((290, 810), str((ch - 1) * 3 + k + 1), fontsize=8)
            y = 80
            if k == 0:
                pg.insert_text((72, 110), f"Chapter {ch}", fontsize=22)
                y = 140
            pg.insert_textbox(pymupdf.Rect(72, y, 520, 780), PROSE * 6, fontsize=11)
    return d


def make_ia_layer():
    """Internet Archive style: page image plus an invisible OCR text layer."""
    d, png = _doc(), _page_png(PROSE * 6)
    for _ in range(3):
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=png)
        pg.insert_textbox(pymupdf.Rect(72, 72, 520, 760), PROSE * 6, fontsize=12, render_mode=3)
    return d


def make_scan(prose=PROSE * 14):
    """Plain scan, no text at all. Full pages of prose, as in a real book."""
    d, png = _doc(), _page_png(prose)
    for _ in range(3):
        pg = d.new_page(); pg.insert_image(pg.rect, stream=png)
    return d


def make_scan_quotes():
    """Scan with dialogue: a word starting with a straight quote made the TSV parser swallow
    the following rows, so OCR coordinates ("5 1 2 1 5 4 402 452 90 61 95.07") filled the book (11-10)."""
    return make_scan(('He looked up. "Stop there, he said, and do not move. ' + PROSE) * 8)


def make_scan_stamped():
    """Scan with a 'Downloaded from' footer: used to come out empty (11-05)."""
    d = make_scan()
    for pg in d:
        pg.insert_text((250, 820), "Downloaded from somelibrary.org", fontsize=7)
    return d


def make_form_scan():
    """Scanned form with one filled field: reddit report 11-05."""
    d, png = _doc(), _page_png("Membership Application Form\n\nPlease fill in all fields below. "
                               "Return the form to the club secretary.\n\nFull name:\n\nAddress:")
    pg = d.new_page(); pg.insert_image(pg.rect, stream=png)
    w = pymupdf.Widget()
    w.field_type, w.field_name = pymupdf.PDF_WIDGET_TYPE_TEXT, "name"
    w.rect, w.field_value = pymupdf.Rect(170, 150, 500, 170), "Jane Doe"
    pg.add_widget(w)
    return d


def make_scan_short_page():
    """Scan whose last page is a short chapter end (a few lines)."""
    d = make_scan()
    pg = d.new_page(); pg.insert_image(pg.rect, stream=_page_png("The end of the short last page. " * 4))
    return d


def make_form_text():
    """Born-digital fillable form."""
    d = _doc(); pg = d.new_page()
    pg.insert_text((72, 60), "Membership Application Form", fontsize=18)
    pg.insert_textbox(pymupdf.Rect(72, 80, 520, 120), "Please fill in all fields below. Return the "
                      "form to the club secretary before the end of the month.", fontsize=10)
    for i, lab in enumerate(["Full name", "Address", "Phone"]):
        pg.insert_text((72, 164 + i * 40), lab + ":", fontsize=11)
        w = pymupdf.Widget()
        w.field_type, w.field_name = pymupdf.PDF_WIDGET_TYPE_TEXT, f"f{i}"
        w.rect, w.field_value = pymupdf.Rect(170, 150 + i * 40, 500, 170 + i * 40), ("Jane Doe" if i == 0 else "")
        pg.add_widget(w)
    return d


def make_comic():
    """Comic: full-page colour art, a speech bubble in the art, a real page number."""
    d = _doc()
    for k in range(4):
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=_page_png(f"Look out, Captain! Page {k + 1}!", color=True))
        pg.insert_text((290, 830), str(k + 1), fontsize=8)
    return d


def make_photo_book():
    """Photo book: full-bleed photos with a one-line caption each."""
    d = _doc()
    for k in range(4):
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=_page_png("", color=True))
        pg.insert_text((72, 820), f"Plate {k + 1}. The harbour at dawn, 1931.", fontsize=9)
    return d


def make_text_with_plates():
    """Born-digital book with two full-page scanned plates in it."""
    d, png = _doc(), _page_png("", color=True)
    for k in range(6):
        pg = d.new_page()
        if k in (2, 4):
            pg.insert_image(pg.rect, stream=png)
        else:
            pg.insert_textbox(pymupdf.Rect(72, 72, 520, 780), PROSE * 6, fontsize=11)
    return d


# Telugu prose written for this test (not from any book). Needs tesseract's "tel" and "osd"
# data locally (the Railway image installs tesseract-ocr-tel) and macOS's Telugu MN font.
TEL = ("ఒక చిన్న గ్రామంలో ఒక రైతు ఉండేవాడు. అతను ప్రతి రోజు ఉదయాన్నే పొలానికి వెళ్ళేవాడు. "
       "సాయంత్రం ఇంటికి వచ్చి పిల్లలకు కథలు చెప్పేవాడు. ")
TEL_FONTS = "/System/Library/Fonts/Supplemental"


def make_legacy_font():
    """Indian-language book in an old non-Unicode font (reddit 11-10, two Telugu novels): the
    page shows Telugu, but the text layer extracts as font codes like "ã¨∂~°º^Õ=~°"."""
    css = '@font-face {font-family: tel; src: url("Telugu MN.ttc");} body {font-family: tel; font-size: 14px;}'
    d = _doc()
    for k in range(4):
        # running header "title + page number" on every page, and a dingbat scene break line
        page = pymupdf.open()
        hp = page.new_page()
        hp.insert_htmlbox(pymupdf.Rect(250, 30, 450, 60), f"<p>మాయ {k + 7}</p>", css=css, archive=pymupdf.Archive(TEL_FONTS))
        hp.insert_htmlbox(pymupdf.Rect(72, 110, 520, 700), "<p>" + TEL * 4 + "</p>", css=css, archive=pymupdf.Archive(TEL_FONTS))
        hp.insert_htmlbox(pymupdf.Rect(200, 710, 450, 740), "<p>ర ర ర ర ర</p>", css=css, archive=pymupdf.Archive(TEL_FONTS))
        png = hp.get_pixmap(dpi=150).tobytes("png")
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=png)
        pg.insert_textbox(pymupdf.Rect(72, 72, 520, 760), "ã¨ÕåÑÏ «û~°O... U„Ñ≤ÖÒ Jã≤ÃÕ =~°Í Åˆ " * 20,
                          fontsize=11, render_mode=3)
    return d


def make_scan_running_head():
    """Scan with a running header and page number on every page (11-10): OCR kept them as
    paragraphs. The PDF's own bookmarks give the chapters."""
    d = _doc()
    for k in range(4):
        src = pymupdf.open().new_page()
        src.insert_text((230, 50), f"THE LONG ROAD    {k + 12}", fontsize=10)
        src.insert_textbox(pymupdf.Rect(72, 90, 520, 760), PROSE * 12, fontsize=12)
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=src.get_pixmap(dpi=150).tobytes("png"))
    d.set_toc([[1, "Part One", 1], [1, "Part Two", 3]])
    return d


HIN = "एक छोटे गाँव में एक किसान रहता था। वह हर सुबह अपने खेत पर जाता था। शाम को वह बच्चों को कहानियाँ सुनाता था। "
PT = ("Ele não está em casa hoje. A canção da manhã começou cedo e a ação continuou. "
      "Você já viu o coração da cidade? Ela disse que não, mas que isso era muito bonito. ")
ES = ("El niño no está en casa. La canción de la mañana empezó temprano y ella dijo que sí, "
      "pero los días eran muy largos y el camino del pueblo estaba lleno de flores. ")


def make_hindi_old_font():
    """Hindi in an old Kruti Dev style font: the text layer is plain ASCII ("dk;Z dj jgs gSa"),
    so only the font name gives it away (11-10)."""
    css = ('@font-face {font-family: dev; src: url("Devanagari Sangam MN.ttc");} '
           'body {font-family: dev; font-size: 15px;}')
    d = _doc()
    for _ in range(3):
        src = pymupdf.open().new_page()
        src.insert_htmlbox(pymupdf.Rect(72, 72, 520, 760), "<p>" + HIN * 11 + "</p>", css=css,
                           archive=pymupdf.Archive(TEL_FONTS))
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=src.get_pixmap(dpi=150).tobytes("png"))
        pg.insert_textbox(pymupdf.Rect(72, 72, 520, 760), "dk;Z dj jgs gSa vkSj ;g ,d NksVk xk¡o gS " * 20,
                          fontsize=11, render_mode=3)
    for pg in d:
        for f in pg.get_fonts():
            d.xref_set_key(f[0], "BaseFont", "/KrutiDev010")
    return d


def make_portuguese_scan():
    """Portuguese scan: read with the English model it lost every ã and ç (11-10)."""
    d, png = _doc(), _page_png(PT * 13)
    for _ in range(3):
        d.new_page().insert_image(pymupdf.Rect(0, 0, 595, 842), stream=png)
    return d


def make_spanish_text():
    d = _doc()
    for _ in range(3):
        d.new_page().insert_textbox(pymupdf.Rect(72, 72, 520, 780), ES * 8, fontsize=11)
    return d


def _tel_png(text, size=14):
    css = '@font-face {font-family: tel; src: url("Telugu MN.ttc");} body {font-family: tel; font-size: %dpx;}' % size
    src = pymupdf.open().new_page()
    src.insert_htmlbox(pymupdf.Rect(72, 72, 520, 760), "<p>" + text + "</p>", css=css, archive=pymupdf.Archive(TEL_FONTS))
    return src.get_pixmap(dpi=150).tobytes("png")


def make_scan_margins():
    """Scan pasted into Word: page image with margins covers ~75% of the page, so it was taken
    for a text PDF with no text and came out empty (11-10 library sample)."""
    d, png = _doc(), _page_png(PROSE * 14)
    for _ in range(3):
        pg = d.new_page(width=612, height=792)
        pg.insert_image(pymupdf.Rect(48, 36, 564, 748), stream=png)
        pg.insert_text((300, 780), " ", fontsize=8)
    return d


def make_ascii_old_font():
    """Telugu in an old font mapped onto ASCII and Latin-1 letters, under a generic font name
    ("F1"): came out as a "Spanish" text book of junk (TL-TTHemalatha, 11-10)."""
    d, png = _doc(), _tel_png(TEL * 5)
    for _ in range(3):
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=png)
        pg.insert_textbox(pymupdf.Rect(72, 72, 520, 760), "NSRV Ligi xqsLi NRPLi ÌÁÕÁ LiÂÁ Fnmsi LRiLigS zmsÖÁy "
                          * 25, fontsize=11, render_mode=3)
    for pg in d:
        for f in pg.get_fonts():
            d.xref_set_key(f[0], "BaseFont", "/F1")
    return d


def make_broken_unicode_telugu():
    """Unicode Telugu made in Word: the page shows the right text, the text layer has vowel signs
    in the wrong order ("చేస్ానానడు"), so the text path copied broken words (11-10)."""
    broken = "".join(TEL[i + 1] + TEL[i] if i + 1 < len(TEL) and "\u0c3e" <= TEL[i + 1] <= "\u0c4d" and i % 3 == 0
                     else TEL[i] for i in range(len(TEL)))
    d, png = _doc(), _tel_png(TEL * 5)
    for _ in range(3):
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=png)
        y, line = 90, (broken * 5)
        for k in range(20):
            pg.insert_text((72, y), line[k * 40:k * 40 + 40], fontfile=TEL_FONTS + "/Telugu MN.ttc", fontname="tel",
                           fontsize=11, render_mode=3)
            y += 30
    return d


def make_magazine_scan():
    """Magazine scan: text above a coloured illustration. The pictures were dropped and only the
    text kept (Chandamama, 11-10); Tesseract's word-free blocks are now cropped as figures."""
    d = _doc()
    for k in range(3):
        src = pymupdf.open().new_page()
        src.insert_textbox(pymupdf.Rect(60, 50, 535, 470), PROSE * 6, fontsize=11)
        src.draw_rect(pymupdf.Rect(80, 500, 515, 790), fill=(0.55, 0.8, 0.95))
        src.draw_circle((200, 640), 70, fill=(0.95, 0.6, 0.2))
        src.draw_oval(pymupdf.Rect(300, 560, 480, 760), fill=(0.3, 0.6, 0.3))
        src.draw_rect(pymupdf.Rect(120, 700, 260, 780), fill=(0.6, 0.3, 0.5))
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=src.get_pixmap(dpi=150).tobytes("png"))
    return d


def make_accented_text():
    """Portuguese prose, accents everywhere: must stay on the text path, not count as font codes."""
    d = _doc()
    for _ in range(3):
        d.new_page().insert_textbox(pymupdf.Rect(72, 72, 520, 780),
            "São João não está à espera da ação. Você já viu a canção do coração? " * 12, fontsize=11)
    return d


# name -> (maker, rules). path / path_in: which pipeline. has / hasnt: phrases. imgs: minimum
# pictures kept. known: problems we know about and accept for now (error prefixes); they print
# as KNOWN instead of failing. When one goes away, the run says so: drop it from known.
# Local runs have no calibre (it is only in the Railway image), so "calibre" means the site
# would serve an image-only EPUB from it.
CASES = {
    "novel": (make_novel, {"path": "text", "has": ["Chapter 1", "Chapter 2", "clocks were striking"],
                           "hasnt": ["NINETEEN EIGHTY-FOUR"], "h_min": 2, "lang": "en"}),
    "ia_layer": (make_ia_layer, {"path": "text", "has": ["clocks were striking"]}),
    # p_max: a scan must not come out one paragraph per printed line (10-23..11-05 bug)
    "scan": (make_scan, {"path": "ocr", "has": ["clocks were striking"], "p_max": 9}),
    "scan_quotes": (make_scan_quotes, {"path": "ocr", "has": ["Stop there", "clocks were striking"],
                                       "hasnt": ["\t", " 1 2 1 "]}),
    "scan_stamped": (make_scan_stamped, {"path": "ocr", "has": ["clocks were striking"], "p_max": 9}),
    # low-ink page: kept as a picture and, since 11-06, its OCR text too
    "scan_short_page": (make_scan_short_page, {"path": "ocr", "has": ["end of the short last page"]}),
    # one short page: OCR text is under 200 chars, used to fall to calibre (reddit 11-06)
    "form_scan": (make_form_scan, {"path": "ocr", "has": ["Membership Application", "Jane Doe"]}),
    # 11-06: title was cut as a "repeated header" on a 1-page PDF; field value ended the page as a heading
    "form_text": (make_form_text, {"path": "text", "has": ["Membership Application Form", "Full name: Jane Doe"],
                                   "h_max": 0}),
    "comic": (make_comic, {"path_in": ["ocr", "calibre"]}),
    "photo_book": (make_photo_book, {"path_in": ["ocr", "calibre"]}),
    "text_with_plates": (make_text_with_plates, {"path": "text", "has": ["clocks were striking"], "imgs": 2,
        "known": ["0 pictures kept"]}),  # _figure_rect skips images over 80% of the page
    # 11-10: legacy-font text layer was copied as junk, and OCR only read English
    "legacy_font": (make_legacy_font, {"path": "ocr", "has": ["గ్రామంలో ఒక రైతు"],
                                       "hasnt": ["ã¨", "Ñ", "మాయ", "యాయ", "ర ర ర"], "lang": "te"}),
    "scan_running_head": (make_scan_running_head, {"path": "ocr", "has": ["clocks were striking"],
                                                   "hasnt": ["LONG ROAD"], "h_min": 2}),
    "accented_text": (make_accented_text, {"path": "text", "has": ["São João não está"], "lang": "pt"}),
    "magazine_scan": (make_magazine_scan, {"path": "ocr", "has": ["clocks were striking"], "imgs": 3}),
    "scan_margins": (make_scan_margins, {"path": "ocr", "has": ["clocks were striking"]}),
    "ascii_old_font": (make_ascii_old_font, {"path": "ocr", "has": ["గ్రామంలో"], "hasnt": ["NSRV"], "lang": "te"}),
    "broken_unicode_telugu": (make_broken_unicode_telugu, {"path": "ocr", "has": ["గ్రామంలో ఒక రైతు"], "lang": "te"}),
    "hindi_old_font": (make_hindi_old_font, {"path": "ocr", "has": ["किसान"], "hasnt": ["dk;Z"], "lang": "hi"}),
    "portuguese_scan": (make_portuguese_scan, {"path": "ocr", "has": ["não está em casa", "canção"], "lang": "pt"}),
    "spanish_text": (make_spanish_text, {"path": "text", "has": ["El niño no está"], "lang": "es"}),
}


def convert(doc):
    """Same choice as /convert: text path, else OCR (paywall and calibre fallback left out)."""
    blocks = _text_blocks(doc)
    if blocks:
        return "text", _structure(blocks, doc)
    pics = {}
    pages = ocr_doc(doc, layout=True, pics=pics) or []
    texts = [t for t, _ in pages]
    if not ocr_ok(texts):
        return "calibre", []  # the site falls back to calibre here: an image-only EPUB
    return "ocr", ocr_chapters(texts, _scan_figures(doc, pages, pics), pdf_toc(doc))


def summary(path, chapters):
    items = [it for ch in chapters for it in ch]
    text = " ".join(t for k, t in items if isinstance(t, str))
    return {"path": path, "chapters": len(chapters),
            "headings": [t for k, t in items if k in ("h1", "h2")][:12],
            "paragraphs": sum(k == "p" for k, _ in items),
            "imgs": sum(k == "img" for k, _ in items),
            "words": len(text.split())}, " ".join(text.split())


def check(name, rules, s, text):
    errs = []
    if "path_in" in rules and s["path"] not in rules["path_in"]:
        errs.append(f"path {s['path']}, want one of {rules['path_in']}")
    if "path" in rules and s["path"] != rules["path"]:
        errs.append(f"path {s['path']}, want {rules['path']}")
    errs += [f"missing {p!r}" for p in rules.get("has", []) if p not in text]
    errs += [f"should be gone: {p!r}" for p in rules.get("hasnt", []) if p in text]
    if s["imgs"] < rules.get("imgs", 0):
        errs.append(f"{s['imgs']} pictures kept, want {rules['imgs']}")
    if s["paragraphs"] > rules.get("p_max", 10**9):
        errs.append(f"{s['paragraphs']} paragraphs, want at most {rules['p_max']} (one per printed line?)")
    if len(s["headings"]) < rules.get("h_min", 0):
        errs.append(f"headings {s['headings']}")
    return errs


def drift(old, new):
    out = []
    for k in new:
        a, b = old.get(k), new[k]
        if k == "words" and a and b and abs(a - b) <= max(5, a * 0.05):
            continue  # ponytail: tesseract versions differ by a word or two
        if a != b:
            out.append(f"{k}: {a} -> {b}")
    return out


def main():
    update = "--update" in sys.argv
    golden = json.loads(GOLDEN.read_text()) if GOLDEN.exists() else {}
    fails, new = [], {}
    for name, (make, rules) in CASES.items():
        doc = pymupdf.open(stream=make().tobytes(), filetype="pdf")
        s, text = summary(*convert(doc))
        new[name] = s
        errs = check(name, rules, s, text)
        if "lang" in rules and (got := ocr_lang(doc)[1] if s["path"] == "ocr" else doc_lang(doc)) != rules["lang"]:
            errs.append(f"epub language {got}, want {rules['lang']}")
        known = [e for e in errs if any(e.startswith(k) for k in rules.get("known", []))]
        errs = [e for e in errs if e not in known]
        for k in rules.get("known", []):
            print(f"     {name}: KNOWN {k}" if any(e.startswith(k) for e in known)
                  else f"     {name}: known issue gone? '{k}' passes now, drop it from known")
        if not update and name in golden:
            errs += [f"changed {d}" for d in drift(golden[name], s)]
        elif not update:
            errs.append("no snapshot yet: run with --update")
        print(f"{'FAIL' if errs else 'ok  '} {name:18} {s['path']:7} ch={s['chapters']} p={s['paragraphs']} "
              f"img={s['imgs']} words={s['words']}")
        fails += [f"  {name}: {e}" for e in errs]
    if update:
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(new, indent=1, ensure_ascii=False) + "\n")
        print(f"snapshot written: {GOLDEN}")
    if fails:
        print("\n".join(fails))
        sys.exit(1)
    print("ok: every kind of PDF converts as before")


if __name__ == "__main__":
    main()
