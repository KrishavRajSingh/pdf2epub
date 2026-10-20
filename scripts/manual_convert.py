"""Convert a PDF on this Mac, with the fixed pipeline, at zero hosting cost.

First customers, done by hand: someone asks for their PDF to be turned into an EPUB, you run this,
you send them the file, you keep their email. No server, no bill, no Railway.

usage: python3 scripts/manual_convert.py book.pdf [-o out.epub] [--title "..."] [--author "..."]
"""
import sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pymupdf
import app as pdf2epub  # same pipeline the site uses


def convert(path: str, out: str | None = None, title: str = "", author: str = "") -> str:
    raw = Path(path).read_bytes()
    doc = pymupdf.open(stream=raw, filetype="pdf")
    blocks = list(pdf2epub._blocks(doc))
    if not blocks:  # scanned: OCR it
        pages = pdf2epub.ocr_doc(doc) or []
        chapters = pdf2epub.ocr_chapters(pages)
        kind = "ocr"
    else:
        chapters = pdf2epub._structure(blocks, doc)
        kind = "text"
    doc.close()
    if not chapters:
        raise SystemExit("nothing readable in that file")
    data = pdf2epub.build_epub(chapters, title or Path(path).stem, author)
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
    convert(a[0], out, title or "", author or "")
