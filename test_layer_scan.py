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


if __name__ == "__main__":
    reread()
    chapters()
    chapter_running_head()
    contents_page_chapters()
    untitled_front_name()
    scan_cover_page()
    preview_contents_page()
