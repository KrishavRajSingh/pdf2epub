"""Convert a PDF on this Mac, with the fixed pipeline, at zero hosting cost.

First customers, done by hand: someone asks for their PDF to be turned into an EPUB, you run this,
you send them the file, you keep their email. No server, no bill, no Railway.

usage: python3 scripts/manual_convert.py book.pdf [-o out.epub] [--title "..."] [--author "..."] [--gdrive]

--gdrive: pages Tesseract reads with low confidence are read again by Google Drive's free OCR
(scripts/gdrive_ocr.py). For Indian-language library jobs; needs the gws login on this Mac.
"""
import sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pymupdf
import app as pdf2epub  # same pipeline the site uses


GDRIVE_CONF = 90  # ponytail: novels average 86-93, magazines 53-75; under 90 Drive reads it better
GDRIVE_THREADS = 6


def _gdrive_pages(doc, layout, confs, lang):
    """Swap Tesseract text for Drive OCR on low-confidence text pages, in place."""
    from concurrent.futures import ThreadPoolExecutor
    from gdrive_ocr import drive_ocr
    # a page Tesseract gave up on (timeout under load) has no words and conf 0: Drive gets it too
    todo = [i for i, (t, _) in enumerate(layout) if confs.get(i, 100) < GDRIVE_CONF
            and (len(t.split()) >= 20 or confs.get(i) == 0)]
    imgs = {}
    for i in todo:  # pymupdf is not thread-safe: render here, upload in threads
        p = doc[i]
        dpi = min(200, int(2000 * 72 / max(p.rect.width, p.rect.height)))
        imgs[i] = p.get_pixmap(dpi=dpi).tobytes("jpg", jpg_quality=88)
    with ThreadPoolExecutor(GDRIVE_THREADS) as ex:
        got = dict(zip(todo, ex.map(lambda i: drive_ocr(imgs[i], lang), todo)))
    ok = 0
    for i, text in got.items():
        n = len(layout[i][0].split())
        if text and len(text.split()) >= (0.5 * n if n >= 20 else 40):
            layout[i] = (text, layout[i][1])
            ok += 1
    print(f"gdrive: {ok}/{len(todo)} low-confidence pages re-read ({len(layout)} pages)")


def convert(path: str, out: str | None = None, title: str = "", author: str = "", gdrive: bool = False) -> str:
    raw = Path(path).read_bytes()
    doc = pymupdf.open(stream=raw, filetype="pdf")
    blocks = pdf2epub._text_blocks(doc)
    lang = "en"
    if not blocks:  # scanned or old-font text: OCR it
        tlang, lang = pdf2epub.ocr_lang(doc)
        pics = {}  # ponytail: same pictures as the site; these scripts used to drop every figure
        confs = {}
        layout = pdf2epub.ocr_doc(doc, layout=True, lang=tlang, pics=pics, confs=confs) or []
        if gdrive and layout:
            _gdrive_pages(doc, layout, confs, lang)
        pages = [t for t, _ in layout]
        chapters = pdf2epub.ocr_chapters(pages, pdf2epub._scan_figures(doc, layout, pics), pdf2epub.pdf_toc(doc))
        kind = "ocr"
    else:
        chapters = pdf2epub._structure(blocks, doc)
        kind = "text"
        lang = pdf2epub.doc_lang(doc)
    doc.close()
    if not chapters:
        raise SystemExit("nothing readable in that file")
    data = pdf2epub.build_epub(chapters, title or Path(path).stem, author, lang)
    dest = Path(out or Path(path).with_suffix(".epub"))
    dest.write_bytes(data)
    heads = [t for ch in chapters for k, t in ch if k in ("h1", "h2")]
    paras = [t for ch in chapters for k, t in ch if k == "p"]
    print(f"mode: {kind}")
    print(f"chapters: {len(chapters)}  headings: {len(heads)}  paragraphs: {len(paras)}")
    for h in heads[:12]:
        print("  -", h[:80])
    print(f"wrote {dest} ({len(data)//1024} KB)")
    return str(dest)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    out = title = author = None
    if "-o" in a:
        i = a.index("-o"); out = a[i + 1]; del a[i:i + 2]
    if "--title" in a:
        i = a.index("--title"); title = a[i + 1]; del a[i:i + 2]
    if "--author" in a:
        i = a.index("--author"); author = a[i + 1]; del a[i:i + 2]
    gd = "--gdrive" in a
    if gd:
        a.remove("--gdrive")
    convert(a[0], out, title or "", author or "", gd)
