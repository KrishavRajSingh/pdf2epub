"""Scans with someone else's OCR layer are read again (davehasl19, The Feasting Dead, 11-21):
blue pen ink painted out, Drive OCR for every reader, AI on inked pages for paid keys, the old
layer kept when Drive fails. And the scan chapter finder on Drive's output: page number and
running head as two paragraphs, drop caps on their own line, a page number "11" read as "II",
a title page split in lines, a ghost of handwriting in CAPS mid-page.

Run: python3 test_layer_scan.py
"""
import os, sys, tempfile
from pathlib import Path

os.environ["LOG_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pymupdf
import app as pdf2epub

LINE = "the quiet house stood on the hill and nobody went near it after dark"


def _layer_doc(n=4, ink=(1,)):
    """Pages of black print with an invisible junk OCR layer; pages in `ink` get a blue pen note."""
    d = pymupdf.open()
    for i in range(n):
        art = pymupdf.open()  # the printed page, flattened to a picture like a scan
        ap = art.new_page(width=320, height=520)
        for k in range(12):
            ap.insert_text((30, 60 + k * 30), LINE[:44], fontsize=10)
        if i in ink:
            ap.draw_line((30, 64), (200, 64), color=(0.1, 0.2, 0.9), width=1.5)
            ap.insert_text((260, 100), "what are", fontsize=12, color=(0.1, 0.2, 0.9))
        png = ap.get_pixmap(dpi=150).tobytes("png")
        pg = d.new_page(width=320, height=520)
        pg.insert_image(pg.rect, stream=png)
        for k in range(12):
            pg.insert_text((30, 60 + k * 30), "strained O* on aXe 073) " + LINE[:20], fontsize=10, render_mode=3)
    return d


def reread():
    d = _layer_doc()
    assert pdf2epub._ocr_layer(d), "fixture must look like an OCR-layer scan"
    img, inked = pdf2epub._strip_pen(d[1])
    assert inked and img[:2] == b"\xff\xd8", "blue ink not found on the annotated page"
    assert not pdf2epub._strip_pen(d[0])[1], "a clean page counted as inked"
    pix = pymupdf.Pixmap(img)
    blue = sum(1 for k in range(0, len(pix.samples), pix.n) if pix.samples[k] < 128)
    assert blue > 0, "print painted out with the ink"

    asked = []
    clean = " ".join([LINE] * 3)

    def drive(img, lang):
        asked.append(lang)
        return clean

    pages = pdf2epub.layer_scan_pages(d, "en", "", drive=drive)
    assert [t for t, _ in pages] == [clean] * 4 and asked == ["en"] * 4, "free reader not read by Drive"

    # paid key: the inked page alone goes to the AI reader, and only it is charged
    pdf2epub.SHELF_KEYS.write_text("cid KEYLIB until=2099-01-01 sharp=5\n")
    pages = pdf2epub.layer_scan_pages(d, "en", "KEYLIB", drive=drive, read=lambda img, l: "ai " + clean)
    assert [t[:3] for t, _ in pages] == ["the", "ai ", "the", "the"], [t[:12] for t, _ in pages]
    assert pdf2epub.sharp_left("KEYLIB") == 4

    # Drive down on most pages: None, the caller keeps the old layer
    assert pdf2epub.layer_scan_pages(d, "en", "", drive=lambda i, l: None) is None
    assert pdf2epub.layer_scan_pages(d, "en", "", drive=None) is None or not pdf2epub.DRIVE_REFRESH
    print("ok — layer scans read again, ink out, AI on inked pages, old layer on failure")


def chapters():
    body = ("It was an afternoon in October and Denis had been sitting with a book upon "
            "his knees for an hour or more, looking out at the lawn and the cedar")
    end = body + ", and"  # a page that ends mid-sentence
    cont = "then he rose and went in without a word to anyone in the house."
    pages = [
        "THE FEASTING\n\nDEAD\n\nJOHN METCALFE\n\nVALANCOURT BOOKS",        # title page in lines
        f"O\n\nI\n\nUR boy, Denis, had at no time been very strong.\n\n{end}",  # drop cap after numeral
        f"6\n\nJOHN METCALFE\n\n{cont}\n\n{body}.",                        # folio then head
        f"THE FEASTING DEAD\n\nII\n\n{body}.\n\nHOW\n\n{body}.",            # "11" read as "II"; ghost CAPS
        f"8\n\nJOHN METCALFE\n\n{body}.",
        f"T\n\nII\n\nHEY were black days that followed.\n\n{body}.",        # drop cap before numeral
        f"THE FEASTING DEAD\n\n9\n\n{body}.",
        f"Q\n\nIII\n\nUESTION and answer between us tumbled.\n\n{body}.",
        f"10\n\nJOHN METCALFE\n\n{body}.",
    ]
    chs = pdf2epub.ocr_chapters(pages)
    heads = [t for c in chs for k, t in c if k == "h1"]
    assert heads == ["THE FEASTING DEAD", "I", "II", "III"], heads
    text = " ".join(t for c in chs for k, t in c if k == "p")
    for good in ("OUR boy", "THEY were", "QUESTION and", end + " " + cont):
        assert good in text, good
    body_text = " ".join(t for c in chs[1:] for k, t in c if k == "p")
    assert "JOHN METCALFE" not in body_text, "running head kept in the chapters"
    print("ok — scan chapters: heads, drop caps, folios, title page, ghosts")


def chapter_running_head():
    """Jon (email 11-21, Unpayable Debt, 328 p scan): left pages carry "22 / CHAPTER 1" as the
    running head. Drive gives it as ["222", "CHAPTER 1", text] (page number read twice or with a
    stray digit) and a line starting "CHAPTER" was never counted as a head, so every left page
    began a chapter: ~150 "CHAPTER 1" entries. The real opener has no page number above it."""
    body = ("the papers would not matter because then and there the law already held that the "
            "enslaved person was property, whatever any document happened to say about it")
    pages = [
        'CHAPTER 1\n\n"Not even by the law here"',                       # opener page, title alone
        f'"Not even by the law here"\n\n21\n\n{body}.',
        f"222\n\nCHAPTER 1\n\n{body}.",                                   # folio misread, then head
        f'"Not even by the law here"\n\n23\n\n{body}.',
        f"24\n\nCHAPTER 1\n\n{body}.",
        f"26\n\n26\n\nCHAPTER 1\n\n{body}.",                              # folio read twice
        f'CHAPTER 2\n\n"a foreign language"\n\n{body}.',                  # opener with text below
        f'"a foreign language"\n\n29\n\n{body}.',
        f"30\n\n303\n\nCHAPTER 2\n\n{body}.",
        f'"a foreign language"\n\n31\n\n{body}.',
    ]
    chs = pdf2epub.ocr_chapters(pages)
    heads = [t for c in chs for k, t in c if k == "h1"]
    assert len(chs) == 2 and all(h.startswith(("CHAPTER 1", "CHAPTER 2")) for h in heads), heads
    text = " ".join(t for c in chs for k, t in c if k == "p")
    assert "CHAPTER" not in text and "222" not in text and "303" not in text, text[:300]
    print("ok — scan chapters: a CHAPTER N running head under the page number")


def contents_page_chapters():
    """Same book: the printed contents page names the sections. An intro "Future Perfect" in plain
    case was no chapter, a frontispiece caption and back-cover ads in CAPS were, back matter
    (BIBLIOGRAPHY on each of its pages) began a chapter per page, and the contents page's own
    lines became chapters."""
    body = ("the papers would not matter because then and there the law already held that the "
            "enslaved person was property, whatever any document happened to say about it")
    pages = [
        "CONTENTS\n\nFuture Perfect\n\n3\n\nCHAPTER 1 \"Not even by the law here\"\n\n5\n\nBIBLIOGRAPHY\n\n9",
        f"CAPITOL AT WASHINGTON-EAST FRONT.\n\nA LOBBYIST.\n\n{body}.",       # frontispiece caption
        "Future Perfect",
        f"Future Perfect\n\n3\n\n{body}.",
        'CHAPTER 1\n\n"Not even by the law here"',
        f'"Not even by the law here"\n\n5\n\n{body}.',
        f"6\n\nCHAPTER 1\n\n{body}.",
        f"BIBLIOGRAPHY\n\n9\n\nAgamben, Giorgio. Homo Sacer. {body}.",
        f"10\n\nBIBLIOGRAPHY\n\nButler, Judith. Bodies That Matter. {body}.",
        f"BIBLIOGRAPHY\n\n11\n\nDouglass, Frederick. {body}.",
        f"THE BLACK TECHNICAL OBJECT:\n\nWHAT WE DO IS SECRET:\n\n{body}.",    # series ad
    ]
    chs = pdf2epub.ocr_chapters(pages)
    heads = [t for c in chs for k, t in c if k == "h1"]
    want = ["Future Perfect", 'CHAPTER 1 "Not even by the law here"', "BIBLIOGRAPHY"]
    assert heads[-3:] == want and len(heads) <= 4, heads
    assert not any("CAPITOL" in h or "SECRET" in h for h in heads), heads
    print("ok — scan chapters: the printed contents page decides the chapters")


def untitled_front_name():
    """The front matter before the first chapter has no heading; the menu showed "ch1"."""
    import io, zipfile, re
    z = zipfile.ZipFile(io.BytesIO(pdf2epub.build_epub([[("p", "cover")], [("h1", "Future Perfect"), ("p", "x")]],
                                                       "Unpayable Debt", "")))
    nav = next(z.read(n).decode() for n in z.namelist() if "nav" in n)
    names = [re.sub(r"\s+", " ", a).strip() for a in re.findall(r"<a[^>]*>(.*?)</a>", nav, re.S)]
    assert names == ["Unpayable Debt", "Future Perfect"], names
    print("ok — untitled front matter is named after the book")


def scan_cover_page():
    """A scan's first page is the cover: a picture, not OCR words read off the artwork."""
    import io, zipfile
    d = pymupdf.open()
    for _ in range(20):
        d.new_page().draw_rect(pymupdf.Rect(50, 50, 300, 400), fill=(0.3, 0.3, 0.3))
    texts = ["Unpayable\n\ndence, the the once deve\n\nDenise Ferreira", "real text " * 30]
    figs = {0: [b"x"]}
    cover = pdf2epub.scan_cover(d, texts, figs)
    assert cover and cover[:2] == b"\xff\xd8" and texts[0] == "" and 0 not in figs
    z = zipfile.ZipFile(io.BytesIO(pdf2epub.build_epub([[("h1", "One"), ("p", "x")]], "Book", "", cover=cover)))
    assert any(n.endswith("cover.jpg") for n in z.namelist()), z.namelist()
    prose = ["word " * 60]
    assert pdf2epub.scan_cover(d, prose) is None and prose[0].startswith("word"), "prose page kept"
    short = pymupdf.open()
    short.new_page()
    form = ["Membership Application\n\nJane Doe"]
    assert pdf2epub.scan_cover(short, form) is None and form[0], "one-page form keeps its text"
    print("ok — scan cover: first page is the cover picture")


def text_pdf_cover():
    """A text PDF whose page 1 is a picture (or a few words) gets it as the cover; prose page 1 does not."""
    d = pymupdf.open()
    p = d.new_page()
    pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 80), 0)
    pm.clear_with(120)
    p.insert_image(p.rect, pixmap=pm)
    for _ in range(25):
        d.new_page().insert_text((72, 72), "body " * 80)
    c = pdf2epub.text_cover(d)
    assert c and c[:2] == b"\xff\xd8"
    t = pymupdf.open()
    # a typeset title page (display type); a half-title in body type is no cover (Jon 11-26, test_cover.py)
    t.new_page().insert_text((72, 100), "The Quiet Harbor", fontsize=30)
    for _ in range(25):
        t.new_page()
    assert pdf2epub.text_cover(t), "title-only page 1 = cover"
    prose = pymupdf.open()
    for _ in range(25):
        pg = prose.new_page()
        for y in range(80, 700, 14):
            pg.insert_text((72, y), "words of a paper that opens on its abstract")
    assert pdf2epub.text_cover(prose) is None, "prose page 1 is no cover"
    short = pymupdf.open()
    short.new_page().insert_image(short[0].rect, pixmap=pm)
    assert pdf2epub.text_cover(short) is None, "short PDF: no cover"
    print("ok — text PDF cover: page 1 picture on the shelf")


def layer_scan_photos():
    """Drive re-read of a layer scan keeps the photos (Ageless Spine 206 -> 0 on 11-25)."""
    import io
    from PIL import Image, ImageDraw
    d = pymupdf.open()
    for k in range(3):
        p = d.new_page(width=400, height=600)
        im = Image.new("RGB", (800, 1200), (245, 240, 230))
        dr = ImageDraw.Draw(im)
        for y in range(100, 1100, 30):
            if not 500 < y < 800:
                dr.rectangle((80, y, 720, y + 12), fill=(30, 30, 30))
        if k == 1:
            for x in range(150, 650, 6):
                dr.line((x, 500, x + 60, 800), fill=(120, 60, 40), width=4)
        b = io.BytesIO()
        im.save(b, "JPEG")
        p.insert_image(p.rect, stream=b.getvalue())
        for y in range(60, 560, 15):
            if not 250 < y < 400:
                p.insert_text((40, y), "the quick brown fox jumps over lazy dogs again", render_mode=3, fontsize=9)
    pics = pdf2epub.layer_pics(d)
    assert list(pics) == [1], pics
    figs = pdf2epub._scan_figures(d, [("text " * 50, 1.0)] * 3, pics)
    assert list(figs) == [1] and len(figs[1]) == 1, figs.keys()
    print("ok — layer scan: photos found for the Drive re-read")


def preview_contents_page():
    """Free preview = first 20 pages. The contents page on page 7 was past the 1/5 window (4 pages),
    so its lines became chapters ("CHAPTER 2 ...", "CHAPTER 4 ...") with nothing in them."""
    body = ("the papers would not matter because then and there the law already held that the "
            "enslaved person was property, whatever any document happened to say about it")
    pages = ["", "Unpayable Debt", "", "", "", "",
             "CONTENTS\n\nFuture Perfect\n\n11\n\nCHAPTER 1 \"Not even\"\n\n19\n\nCHAPTER 2 \"hallucination\"\n\n83",
             "", "", "", "", "", "Future Perfect"] + [f"Future Perfect\n\n{13 + k}\n\n{body}." for k in range(7)]
    chs = pdf2epub.ocr_chapters(pages)
    heads = [t for c in chs for k, t in c if k == "h1"]
    assert heads == ["Future Perfect"], heads
    print("ok — scan chapters: contents page found in a 20-page preview")


def contents_heading_not_first():
    """Ageless Spine via Drive OCR (11-22): "CONTENTS" came fifth on its page, the second contents
    page had no heading, and the entries are spelled "Acknowlegements"/"Forward". Every dotted line
    became a chapter, and the real ACKNOWLEDGMENTS and FOREWORD were dropped."""
    body = ("the spine was never meant to be held stiff and upright by effort, it was meant to rest "
            "on the bones below it, the way stones rest in an arch that stands for a thousand years")
    pages = ["", "", "",
             "Acknowlegements\n\nForward...........\n\nCONTENTS\n\nPART I - A Body of Knowledge\n\nVII\n\n"
             "Chapter One - The Shape We're In...\n\nChapter Two - Design for Life............\n\n3\n\n15",
             "Goose Neck........\n\nOpen Your Eyes..........\n\nPART III - Putting It All Together..\n\n"
             "How to Sit\n\nHow to Stand..\n\nHow to Walk..\n\nIndex...\n\n165",
             f"ACKNOWLEDGMENTS\n\n{body}.", f"{body}.", f"FOREWORD\n\n{body}.", f"{body}.",
             f"Chapter One\n\nThe Shape We're In\n\n{body}.", f"{body}."]
    chs = pdf2epub.ocr_chapters(pages)
    heads = [t for c in chs for k, t in c if k == "h1"]
    assert heads == ["ACKNOWLEDGMENTS", "FOREWORD", "Chapter One The Shape We're In"], heads
    print("ok — scan chapters: contents heading mid-page, dotted second page, near spellings")


def drive_drop_caps():
    """Drive loses a two-line drop cap like the old layer does ("ere's a quick start", Ageless Spine
    11-22). The letter comes back from the picture only; no word list decides (user, 11-23): a
    line printed lowercase on purpose at the margin, a sidebar's frame line and a line Drive read
    with its capital already all stay as they are."""
    body = "a quick start to understanding this whole book is to lie down on the floor and rest. " * 4
    d = pymupdf.open()
    layer = []
    for k in range(3):
        art = pymupdf.open()
        ap = art.new_page()
        if k == 0:  # drop cap H beside the first two lines
            ap.insert_text((72, 186), "H", fontsize=44)
            ap.insert_textbox(pymupdf.Rect(110, 150, 520, 190), "ere's " + body[:80], fontsize=11)
            ap.insert_textbox(pymupdf.Rect(72, 192, 520, 700), body, fontsize=11)
            layer.append([(pymupdf.Rect(110, 150, 520, 190), "ere's " + body[:80]),
                          (pymupdf.Rect(72, 192, 520, 700), body)])
        elif k == 1:  # a sidebar box: its frame line sits left of an indented lowercase line
            ap.draw_rect(pymupdf.Rect(80, 140, 520, 330), color=(0.2, 0.5, 0.5), width=1)
            ap.insert_textbox(pymupdf.Rect(110, 150, 500, 320), "injury or pain. " + body[:150], fontsize=11)
            ap.insert_textbox(pymupdf.Rect(72, 360, 520, 700), body, fontsize=11)
            layer.append([(pymupdf.Rect(110, 150, 500, 320), "injury or pain. " + body[:150]),
                          (pymupdf.Rect(72, 360, 520, 700), body)])
        else:  # lowercase on purpose, at the margin
            ap.insert_textbox(pymupdf.Rect(72, 150, 520, 700), "e. e. cummings wrote " + body, fontsize=11)
            layer.append([(pymupdf.Rect(72, 150, 520, 700), "e. e. cummings wrote " + body)])
        pg = d.new_page()
        pg.insert_image(pg.rect, stream=ap.get_pixmap(dpi=150).tobytes("png"))
        for r, t in layer[-1]:
            pg.insert_textbox(r, t, fontsize=11, render_mode=3)
    said = ["ere's " + body, "injury or pain. " + body, "e. e. cummings wrote " + body]
    it = iter(said)
    got = [t for t, _ in pdf2epub.layer_scan_pages(d, "en", "", drive=lambda img, l: next(it))]
    assert got[0].startswith("Here's a quick start"), got[0][:30]
    assert got[1:] == said[1:], [g[:20] for g in got[1:]]
    it = iter(["Here's " + body] + said[1:])  # Drive already read the capital: no second one
    got = [t for t, _ in pdf2epub.layer_scan_pages(d, "en", "", drive=lambda img, l: next(it))]
    assert got[0].startswith("Here's a quick"), got[0][:30]
    print("ok — Drive path: drop cap read off the picture, frame lines and lowercase text left alone")


def front_matter_and_caps_title():
    """Signal to Noise via Drive (davehasl19, 11-23): the cover's ISBN, the back-cover review quote,
    the "Other Avon Books by" list and the copyright page were chapters, and the chapter's drop cap
    "T" (its own line, before "2" and the title) was glued onto the title: "TJACKKNIFED", "he hum"."""
    body = ("the taxi crossed the bridge in the rain and the driver said nothing at all about the "
            "fare or the weather or the way the city lights shook on the black water below them")
    pages = ["ISBN 0-380-79292-3\n\n9780380792924",
             '"A BRAVE NEW VISION OF THE FUTURE...WELL-CONCEIVED AND\n\n' + body + ".",
             "Other Avon Books by Eric S. Nylund\n\nDRY WATER\n\nA GAME OF UNIVERSE",
             "AVON BOOKS, INC.\n\nISBN: 0-380-79292-3\n\nWCD 10 9 8 7 6 5 4 3 2 1",
             "T\n\n2\n\nJACKKNIFED\n\nhe hum of the taxi was in Jack's head.\n\n" + body + ".",
             body + "."]
    chs = pdf2epub.ocr_chapters(pages)
    heads = [t for c in chs for k, t in c if k == "h1"]
    assert heads == ["JACKKNIFED"], heads
    text = [t for c in chs for k, t in c if k == "p"]
    assert any(t.startswith("The hum of the taxi") for t in text), text
    print("ok — scan chapters: no chapters from cover/copyright/also-by pages, drop cap not on the title")


def anthology_contents():
    """Tales of Terror (11-24): numbered contents ("III. THE CORPSE LIGHT 51"), an entry split over
    lines, story numerals under the running head, quoted titles, running heads with page numbers
    and a sequel whose pages carry the first story's title."""
    body = "It was a dark night and the wind howled about the old house on the moor for hours. " * 6
    pages = [
        "CONTENTS\n\n1.\n\nTHE WOMAN WITH THE\n\nOILY EYES'\n\nII.\n\nTHE STORY OF ANNETTE THE WOMAN WITH THE\n\n"
        "BEING THE SEQUEL TO\n\n41\n\nIII. THE CORPSE LIGHT\n\n51\n\nIV. THE RED LILY.\n\n66\n\nV.\n\nTHE PIRATE'S TREASURE\n\n95",
        "TALES OF TERROR\n\nI\n\nTHE WOMAN WITH THE OILY EYES'\n\nALTHOUGH often urged. " + body,
        "THE WOMAN WITH THE 'OILY EYES' II\n\n" + body,
        "41\n\nII\n\nSEQUEL TO THE WOMAN WITH THE\n\n'OILY EYES'\n\nTHE STORY OF ANNETTE\n\n" + body,
        "THE WOMAN WITH THE 'OILY EYES' 43\n\n" + body,
        "51\n\nIII.\n\nTHE CORPSE LIGHT,\n\n" + body,
        "66\n\nTALES OF TERROR\n\nIV\n\n'RED LILY'\n\n" + body,
        "'RED LILY'\n\n67\n\n" + body,
        "95\n\nV\n\nTHE PIRATE'S TREASURE\n\nAT the time the events occurred. " + body,
        "THE PIRATE'S TREASURE 97\n\n" + body,
    ] + ["TALES OF TERROR\n\n" + body] * 6
    chs = pdf2epub.ocr_chapters(pages)
    heads = [t for ch in chs for k, t in ch if k == "h1"]
    want = ["OILY EYES", "ANNETTE", "CORPSE LIGHT", "RED LILY", "PIRATE"]
    assert len(heads) == 5 and all(w in h for w, h in zip(want, heads)), heads
    text = " ".join(t for ch in chs for k, t in ch if k == "p")
    assert "IALTHOUGH" not in text and "VAT the" not in text and "AT the time" in text, text[:300]


def page_end_hyphen():
    """A word split at the page foot ("com-" / "pany") whose faint hyphen Drive read as "com.":
    the picture says hyphen, so the word joins and the paragraph goes on (davehasl19, Tales of
    Terror 11-26). A real full stop at the foot, before a lowercase page, stays a full stop."""
    def doc(last):
        d = pymupdf.open()
        for words in (["She", "had", "been", "chartered", "by", "a", "Glasgow", last], ["pany,", "and", "was"]):
            art = pymupdf.open()
            ap = art.new_page(width=320, height=520)
            ap.insert_text((30, 480), " ".join(words), fontsize=11, fontname="tiro")
            png = ap.get_pixmap(dpi=200).tobytes("png")
            pg = d.new_page(width=320, height=520)
            pg.insert_image(pg.rect, stream=png)
            pg.insert_text((30, 480), " ".join(words), fontsize=11, fontname="tiro", render_mode=3)
        return d
    nxt = "TALES OF TERROR\npany, and was then loading up at the West Quay."
    d = doc("com-")
    got = pdf2epub._page_end_hyphen(d[0], "She had been chartered by a Glasgow com.", nxt)
    assert got.endswith("Glasgow com-"), got
    paras = [t for ch in pdf2epub.ocr_chapters(["STORY\n" + got, nxt.split("\n", 1)[1]]) for k, t in ch if k == "p"]
    assert any("Glasgow company, and was" in t for t in paras), paras
    d = doc("men.")
    got = pdf2epub._page_end_hyphen(d[0], "She had been chartered by a Glasgow men.", nxt)
    assert got.endswith("Glasgow men."), got
    print("ok page_end_hyphen")


if __name__ == "__main__":
    page_end_hyphen()
    anthology_contents()
    reread()
    chapters()
    chapter_running_head()
    contents_page_chapters()
    untitled_front_name()
    scan_cover_page()
    text_pdf_cover()
    layer_scan_photos()
    preview_contents_page()
    contents_heading_not_first()
    drive_drop_caps()
    front_matter_and_caps_title()
