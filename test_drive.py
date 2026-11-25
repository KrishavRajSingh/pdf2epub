"""Paid keys: low-confidence OCR pages are read again by Google Drive's free OCR first; pages Drive
fails on go to the AI re-read when the key has Library pages left (ysvsr, 11-18).

Run: python3 test_drive.py
"""
import os, sys, tempfile
from pathlib import Path

os.environ["LOG_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pymupdf
import app as pdf2epub


def main():
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page()
    words = " ".join(["tess"] * 30)
    layout = [(words, 0.5), (words, 0.5), (words, 0.5)]
    confs = {0: 95.0, 1: 70.0, 2: 60.0}
    drive_text = " ".join(["drive"] * 30)
    ai_text = " ".join(["sharp"] * 30)
    asked = []

    def drive(img, lang):
        asked.append(lang)
        return drive_text

    # Batch pass (no AI pages): Drive still re-reads every unsure page, free
    pdf2epub.SHELF_KEYS.write_text("cid1 KEYBATCH until=2099-01-01\ncid2 KEYLIB until=2099-01-01 sharp=5\n")
    lay = list(layout)
    assert pdf2epub.reread_pages(doc, lay, dict(confs), "te", "KEYBATCH", drive=drive, read=lambda i, l: ai_text) == 2
    assert lay[0][0] == words and lay[1][0] == drive_text and lay[2][0] == drive_text
    assert asked == ["te", "te"]

    # Drive fails on one page: the Library budget covers it, and only that page is charged
    def flaky(img, lang):
        flaky.n += 1
        return drive_text if flaky.n == 1 else None
    flaky.n = 0
    lay = list(layout)
    assert pdf2epub.reread_pages(doc, lay, dict(confs), "te", "KEYLIB", drive=flaky, read=lambda i, l: ai_text) == 2
    assert sorted(t for t, _ in lay[1:]) == [drive_text, ai_text]
    assert pdf2epub.sharp_left("KEYLIB") == 4

    # Drive down and no AI pages: Tesseract text stays
    lay = list(layout)
    assert pdf2epub.reread_pages(doc, lay, dict(confs), "te", "KEYBATCH", drive=lambda i, l: None) == 0
    assert lay == layout

    # One-book buyer ($3/$5 checkout, no key): Drive still re-reads unsure pages, no AI pages (11-23)
    lay = list(layout)
    asked.clear()
    assert pdf2epub.reread_pages(doc, lay, dict(confs), "en", "", drive=drive, read=lambda i, l: ai_text) == 2
    assert lay[1][0] == drive_text and asked == ["en", "en"]
    import inspect
    assert "if paid and pages:\n                    reread_pages(" in inspect.getsource(pdf2epub.convert), \
        "paid scans without a key must get the Drive re-read"

    # Drive's export: BOM, a "____" rule where the image sat, one paragraph per line
    assert pdf2epub._drive_clean("﻿________________\n\nమొదటి పేరా\nరెండో పేరా\n") == "మొదటి పేరా\n\nరెండో పేరా"
    print("ok: drive")


if __name__ == "__main__":
    main()
