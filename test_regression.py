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


def make_ia_photos_heads():
    """reddit 11-18 (Spiritual-Willow2778): Internet Archive scans of a photo book and a memoir.
    Photos printed in the page image were all dropped (the page is one big image); running heads
    alternate book title / chapter title, so neither was on half the pages and both came out as
    headings on every page; the chapter title in a display face OCRed to junk."""
    d = _doc()
    for k in range(8):
        src = pymupdf.open().new_page()
        src.insert_text((230, 40), "SLOW WATERS" if k % 2 else "THE RIVER BOOK", fontsize=10)
        top = 90
        if k == 0:
            src.insert_text((200, 120), "SLOW WATERS", fontsize=22)
            top = 160
        if k in (2, 5):  # a photo between paragraphs
            src.draw_rect(pymupdf.Rect(150, 300, 450, 520), fill=(0.55, 0.35, 0.25))
            src.draw_circle((300, 410), 70, fill=(0.15, 0.3, 0.5))
            src.insert_textbox(pymupdf.Rect(72, top, 520, 290), PROSE * 3, fontsize=12)
            src.insert_textbox(pymupdf.Rect(72, 540, 520, 760), PROSE * 3, fontsize=12)
        else:
            src.insert_textbox(pymupdf.Rect(72, top, 520, 760), PROSE * 9, fontsize=12)
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=src.get_pixmap(dpi=150).tobytes("png"))
        pg.insert_text((230, 40), "SLOW WATERS" if k % 2 else "THE RIVER BOOK", fontsize=10, render_mode=3)
        if k == 0:
            pg.insert_text((200, 120), "SL0W VVATFRS", fontsize=22, render_mode=3)
        if k in (2, 5):
            pg.insert_textbox(pymupdf.Rect(72, top, 520, 290), PROSE * 3, fontsize=12, render_mode=3)
            pg.insert_textbox(pymupdf.Rect(72, 540, 520, 760), PROSE * 3, fontsize=12, render_mode=3)
            pg.insert_text((200, 400), "~ gf ,.\\ ;", fontsize=9, render_mode=3)  # OCR read the photo
        else:
            pg.insert_textbox(pymupdf.Rect(72, top, 520, 760), PROSE * 9, fontsize=12, render_mode=3)
    return d


def make_ia_two_layer():
    """reddit 11-18 (Spiritual-Willow2778, Ageless Spine): Internet Archive pages are a low-res
    picture layer (paper, photos, drawings) under a masked layer holding only the letters. Thin
    light anatomy drawings and people cut out on white have little dark ink; found on the picture
    layer they are kept, and the letters on top never pass for a picture."""
    d = _doc()
    for k in range(4):
        bg = pymupdf.open().new_page()
        bg.draw_rect(bg.rect, fill=(0.93, 0.92, 0.9), color=None)
        if k in (1, 2):  # a thin light-red line drawing between paragraphs
            for j in range(12):
                bg.draw_line((250 + j * 8, 320), (300 + (j % 3) * 20, 560), color=(0.85, 0.55, 0.5), width=1.2)
            bg.draw_circle((300, 300), 22, color=(0.85, 0.55, 0.5), width=1.2)
        fg = pymupdf.open().new_page()
        fg.insert_textbox(pymupdf.Rect(72, 72, 520, 260), PROSE * 3, fontsize=12)
        fg.insert_textbox(pymupdf.Rect(72, 600, 520, 780), PROSE * 2, fontsize=12)
        ink = fg.get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
        alpha = pymupdf.Pixmap(pymupdf.csGRAY, ink.irect, False)
        alpha.set_rect(alpha.irect, (0,))
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=bg.get_pixmap(dpi=50).tobytes("jpg"))
        black = pymupdf.Pixmap(pymupdf.csGRAY, ink.irect, False)
        black.set_rect(black.irect, (0,))
        mask = pymupdf.Pixmap(ink.tobytes("png"))
        mask.invert_irect()
        pg.insert_image(pg.rect, stream=black.tobytes("png"), mask=mask.tobytes("png"))
        pg.insert_textbox(pymupdf.Rect(72, 72, 520, 260), PROSE * 3, fontsize=12, render_mode=3)
        pg.insert_textbox(pymupdf.Rect(72, 600, 520, 780), PROSE * 2, fontsize=12, render_mode=3)
    return d


def make_ia_memoir():
    """Internet Archive scan like Marcela's Divine Challenge (11-14): chapter lines in body type
    ("Chapter | - Childhood", OCR read the 1 as |), Bible verses set big, and a handwritten
    letter whose OCR is junk. Came out as 207 chapters, one per verse or letter line."""
    d, png = _doc(), _page_png(PROSE * 6)
    junk = "Gue Sf hewW muck gar Lthw aad anch ttm vaihd Yete Pande fhe COitsee aclecn tft Arsene " * 4
    verses = ["27What I tell you in darkness, that speak ye in light.",
              "31Fear ye not therefore, ye are of more value than many sparrows.",
              "32Whosoever therefore shall confess me before men, him will I confess also."]
    heads = {2: "Chapter | - Childhood", 12: "Chapter 2 - The Convent", 22: "Chapter 3 - The Trial"}
    for i in range(32):
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=png)
        if i == 1:
            for j, v in enumerate(verses):
                pg.insert_textbox(pymupdf.Rect(72, 72 + j * 90, 520, 160 + j * 90), v, fontsize=17, render_mode=3)
            pg.insert_textbox(pymupdf.Rect(72, 360, 520, 760), PROSE * 3, fontsize=11, render_mode=3)
            continue
        if i == 27:
            pg.insert_textbox(pymupdf.Rect(72, 72, 520, 760), junk, fontsize=11, render_mode=3)
            continue
        top = 72
        if i in heads:
            pg.insert_textbox(pymupdf.Rect(72, 72, 520, 100), heads[i], fontsize=11, render_mode=3)
            top = 120
        pg.insert_textbox(pymupdf.Rect(72, top, 520, 760), PROSE * 5, fontsize=11, render_mode=3)
    return d


def make_ia_word_lines():
    """Internet Archive scan whose OCR layer (LuraDocument, reddit 11-18 novel) stores a justified
    line as one "line" per word and guesses a size per word (4-11pt). Each word was a line and
    any line with one big word a heading: 954 chapters. Chapter titles are one word in capitals
    under a bare number, so they appear once and failed the recurring-words junk check."""
    import random
    rnd = random.Random(7)
    d, png = _doc(), _page_png(PROSE * 6)
    words = (PROSE * 30).split()
    heads = {0: "JACKKNIFED", 10: "APPLEJACK", 20: "CRACKERJACK"}
    k = 0
    for i in range(30):
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=png)
        y = 80
        if i in heads:
            pg.insert_text((290, y), str(len([h for h in heads if h <= i])), fontsize=9, render_mode=3)
            pg.insert_text((200, y + 30), heads[i], fontsize=12, render_mode=3)
            y += 70
        for line in range(40):
            x = 90 if line % 8 == 0 else 72  # paragraph first lines indented
            while x < 480:
                w = words[k % len(words)]
                k += 1
                size = rnd.uniform(9.5, 11.5) if line % 8 == 0 else rnd.uniform(5.5, 8.5)
                pg.insert_text((x, y), w, fontsize=size, render_mode=3)
                x += len(w) * 5 + 14
            y += 16
    return d


def make_ia_anthology():
    """Anthology scan with an OCR layer (reddit 11-19, 552 pages, 30 stories in 5 chapters).
    Introduction / Preface / Prologue counted as "Chapter N" lines, so the scan split on those
    only and story titles never started a chapter. The running head's page number OCRs as junk
    ("go The Long Road", "4612 The Long Road") so it never repeats; set big it became a heading. A title
    ends in an OCR "!" or starts with an ornament read as "¥ "."""
    d, png = _doc(), _page_png(PROSE * 6)
    lines = [PROSE[i:i + 60] for i in range(0, len(PROSE) - 60, 60)] * 4
    heads = {0: "INTRODUCTION", 1: "PREFACE", 2: "PROLOGUE", 3: "THE TRUMPET SOUNDS",
             7: "A SPOILED PRIEST!", 11: "¥ BLACK ROCK"}
    nums = ["go", "4612", "1p", "Za", "58", "60"]
    for i in range(15):
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=png)
        pg.insert_text((200, 22), f"{nums[i % len(nums)]} The Long Road Home",
                       fontsize=12 if i % 3 == 0 else 9.8, render_mode=3)
        y = 90
        if i in heads:
            pg.insert_text((180, y), heads[i], fontsize=14, render_mode=3)
            y += 50
        for k, ln in enumerate(lines[:36]):
            pg.insert_text((72, y), ln, fontsize=10, render_mode=3)
            y += 18 if k % 6 != 5 else 26
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


def make_control_code_layer():
    """English scan whose OCR layer (PDF24 Tools - OCR) extracts as ASCII control codes:
    "\x02\x05\x01˖ \x16\x01\x04\x14\x05˖". The non-ASCII junk check scored it 0.12 and the text
    path built an EPUB of junk (The Stranger, mailed 11-16)."""
    d, png = _doc(), _page_png(PROSE * 14)
    junk = "\x02\x05\x01 \x16\x01\x04\x14\x05 \x06\x06\x03\x07 \x07\x10 \x0c\x13 \x05\x01\x12 \x04\x0e "
    for _ in range(3):
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=png)
        pg.insert_textbox(pymupdf.Rect(72, 72, 520, 760), junk * 40, fontsize=11, render_mode=3)
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


def make_blank_layer_telugu():
    """Telugu in a font whose glyphs have no Unicode map (Gautami via iText, Loya Nunchi
    Sikharaniki, 11-18): the page shows Telugu, the text layer is 98% spaces with a stray
    అ, ి or త, and the text path built an EPUB of lone letters."""
    d, png = _doc(), _tel_png(TEL * 5)
    stray = ("        అ      ి     " + " " * 40 + "\n" + " " * 55 + "త  \n") * 30
    for _ in range(3):
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=png)
        pg.insert_textbox(pymupdf.Rect(30, 30, 580, 820), stray, fontfile=TEL_FONTS + "/Telugu MN.ttc",
                          fontname="tel", fontsize=8, render_mode=3)
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


def make_paper():
    """Journal offprint (reddit 11-16, Springer AI & Society): offprint cover + notice pages,
    10pt body, short 10pt verse lines, 8.5pt footnotes with one carried over as "Footnote 1
    (continued)", and an 8.5pt reference list with hanging indents. The small blocks outnumber
    the body blocks, which made every verse line a heading."""
    d = _doc()
    d.new_page().insert_text((72, 200), "A Paper About Golems", fontsize=24)
    d.new_page().insert_textbox(pymupdf.Rect(72, 72, 520, 300),
        "Your article is protected by copyright. This e-offprint is for personal use only.", fontsize=11)
    for k in range(3):
        pg = d.new_page()
        if k == 0:
            pg.insert_text((72, 90), "A Paper About Golems", fontsize=16)
        if k == 1:  # a section starts before note 1 carries on, so note 1 sits in the last chapter
            pg.insert_text((72, 90), "2 The Sorcerer's Apprentice", fontsize=12)
        pg.insert_textbox(pymupdf.Rect(72, 110, 520, 300), PROSE * 4, fontsize=10)
        for j, line in enumerate(("I like to think", "of a cybernetic meadow", "where mammals and computers")):
            pg.insert_text((100, 320 + j * 14), line, fontsize=10)
        pg.insert_textbox(pymupdf.Rect(72, 370, 520, 520), PROSE * 3, fontsize=10)
        y = 560
        if k == 1:  # 11-18: label and text are separate blocks, and the prose above ends mid-sentence
            pg.insert_text((72, 535), "and the machines were explicitly touched upon, not", fontsize=10)
            pg.insert_text((72, y), "Footnote 1 (continued)", fontsize=8.5)
            pg.insert_text((72, y + 22), "and the golem story goes on here.", fontsize=8.5)
            y += 44
        for n in range(3):
            pg.insert_text((72, y), f"{k * 3 + n + 1} A note about golems and machines, number {k * 3 + n + 1}.",
                           fontsize=8.5)
            y += 16
    for _ in range(3):  # text set high on the page, like the Springer paper (starts at y=54)
        d.new_page().insert_textbox(pymupdf.Rect(72, 46, 520, 700), PROSE * 9, fontsize=10)
    pg = d.new_page()
    pg.insert_text((72, 80), "References", fontsize=12)
    y = 100
    for n in range(14):
        pg.insert_text((72, y), f"Author{chr(65 + n)} X (2019) A long title of a book about thinking", fontsize=8.5)
        pg.insert_text((90, y + 11), "machines. Some Press, Cambridge", fontsize=8.5)
        y += 24
    # 11-18: a short entry first on the next page was cut as a "running head" (y < 60, has digits)
    pg = d.new_page()
    pg.insert_text((300, 30), "AI & SOCIETY (2020) 35:1009", fontsize=8.5)
    pg.insert_text((72, 62), "Lancaster BL (1997) The golem as a transpersonal image 1(3):5", fontsize=8.5)
    pg.insert_text((72, 86), "Latour B (1987) Science in action. Harvard University Press", fontsize=8.5)
    return d


# name -> (maker, rules). path / path_in: which pipeline. has / hasnt: phrases. imgs: minimum
# pictures kept. known: problems we know about and accept for now (error prefixes); they print
# as KNOWN instead of failing. When one goes away, the run says so: drop it from known.
# Local runs have no calibre (it is only in the Railway image), so "calibre" means the site
# would serve an image-only EPUB from it.
def make_math_paper():
    """Preprint with display equations (11-19 lead, two papers "did not convert well"): equations
    in a math font with a number at the right margin, a footer whose page number changes, and a
    page with two figures and prose between them (a 1999 journal paper lost 4 of its 6 figures)."""
    d = _doc()
    pic = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 80), 0)
    pic.set_rect(pic.irect, (40, 90, 160))
    for k in range(3):
        pg = d.new_page()
        if k == 2:
            pg.insert_image(pymupdf.Rect(100, 60, 500, 200), pixmap=pic)
            pg.insert_textbox(pymupdf.Rect(72, 215, 520, 400), PROSE * 3, fontsize=10)
            pg.insert_image(pymupdf.Rect(100, 420, 500, 560), pixmap=pic)
            pg.insert_textbox(pymupdf.Rect(72, 580, 520, 780), PROSE * 2 + "and the paper ends", fontsize=10)
        else:
            pg.insert_textbox(pymupdf.Rect(72, 72, 520, 260), PROSE * 4, fontsize=10)
            pg.insert_text((180, 290), "a = b + g", fontname="symb", fontsize=12)
            pg.insert_text((490, 290), f"({k + 1})", fontsize=10)
            pg.insert_textbox(pymupdf.Rect(72, 320, 520, 790), PROSE * 9 + "and so the sentence runs on to", fontsize=10)
        pg.insert_text((72, 815), f"Smith and Jones: Preprint submitted to Elsevier Page {k + 1} of 3", fontsize=8)
    return d


CASES = {
    # 11-19 lead: equations as pictures, footer "Page N of M" gone, both figures on page 3 kept
    "math_paper": (make_math_paper, {"path": "text", "has": ["clocks were striking", "and the paper ends"],
                                     "hasnt": ["Preprint submitted", "a = b + g", "α = β"], "imgs": 4}),
    "novel": (make_novel, {"path": "text", "has": ["Chapter 1", "Chapter 2", "clocks were striking"],
                           "hasnt": ["NINETEEN EIGHTY-FOUR"], "h_min": 2, "lang": "en"}),
    "ia_layer": (make_ia_layer, {"path": "text", "has": ["clocks were striking"]}),
    "ia_two_layer": (make_ia_two_layer, {"path": "text", "has": ["clocks were striking"], "imgs": 2}),
    "ia_photos_heads": (make_ia_photos_heads, {"path": "text", "has": ["SLOW WATERS", "clocks were striking"],
                                               "hasnt": ["THE RIVER BOOK", "SL0W", "gf ,."], "imgs": 2,
                                               "ch_max": 2}),
    # ch_max: verses and letter lines set big must not each start a chapter (Marcela 11-14)
    "ia_memoir": (make_ia_memoir, {"path": "text", "has": ["Chapter 1 - Childhood", "Chapter 3 - The Trial",
                                                        "many sparrows"],
                                   "hasnt": ["hewW", "Chapter | -"], "ch_max": 4, "imgs": 1}),
    # 11-18: one OCR "line" per word with a random size each: every paragraph start was a chapter
    "ia_word_lines": (make_ia_word_lines, {"path": "text", "has": ["JACKKNIFED", "CRACKERJACK",
                                                                "the clocks were striking thirteen"],
                                           "ch_max": 4, "h_min": 3}),
    # 11-19: an anthology's stories each start a chapter, running heads with junk page numbers gone
    "ia_anthology": (make_ia_anthology, {"path": "text", "has": ["THE TRUMPET SOUNDS", "A SPOILED PRIEST",
                                                              "BLACK ROCK"],
                                         "hasnt": ["The Long Road Home", "¥"], "ch_min": 6}),
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
    "control_code_layer": (make_control_code_layer, {"path": "ocr", "has": ["clocks were striking"], "lang": "en"}),
    "broken_unicode_telugu": (make_broken_unicode_telugu, {"path": "ocr", "has": ["గ్రామంలో ఒక రైతు"], "lang": "te"}),
    "blank_layer_telugu": (make_blank_layer_telugu, {"path": "ocr", "has": ["గ్రామంలో ఒక రైతు"], "lang": "te"}),
    "hindi_old_font": (make_hindi_old_font, {"path": "ocr", "has": ["किसान"], "hasnt": ["dk;Z"], "lang": "hi"}),
    "portuguese_scan": (make_portuguese_scan, {"path": "ocr", "has": ["não está em casa", "canção"], "lang": "pt"}),
    "spanish_text": (make_spanish_text, {"path": "text", "has": ["El niño no está"], "lang": "es"}),
    # 11-16: verse lines became chapters, footnotes sat in the text, references ran together
    "paper": (make_paper, {"path": "text", "ch_max": 3, "hasnt": ["e-offprint", "Footnote 1 (continued)", "touched upon, not and the golem", "AI & SOCIETY"],
                           "has": ["I like to think"],
                           "para": ["AuthorA X (2019) A long title of a book about thinking machines. Some Press, Cambridge",
                                    "Lancaster BL (1997) The golem as a transpersonal image 1(3):5"],
                           "fn": ["1 A note about golems and machines, number 1. and the golem story goes on here."]}),
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
    if s["chapters"] > rules.get("ch_max", 10**9):
        errs.append(f"{s['chapters']} chapters, want at most {rules['ch_max']}: {s['headings']}")
    if s["chapters"] < rules.get("ch_min", 0):
        errs.append(f"{s['chapters']} chapters, want at least {rules['ch_min']}: {s['headings']}")
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
        path, chapters = convert(doc)
        s, text = summary(path, chapters)
        new[name] = s
        errs = check(name, rules, s, text)
        items = [it for ch in chapters for it in ch]
        for kind, key in (("p", "para"), ("fn", "fn")):  # whole paragraphs / notes, not phrases
            errs += [f"no {kind} block {p!r}" for p in rules.get(key, []) if (kind, p) not in items]
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
