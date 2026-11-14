"""Library pass: low-confidence OCR pages get the vision model's text, within the key's page budget.

Run: python3 test_sharp.py
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
    good = " ".join(["sharp"] * 30)
    calls = []

    def read(img, lang):
        calls.append(lang)
        return good

    # no key line → no budget, nothing swapped
    assert pdf2epub.sharp_left("nokey") == 0
    assert pdf2epub.sharp_pages(doc, list(layout), confs, "te", "nokey", read) == 0

    pdf2epub.SHELF_KEYS.write_text("cid1 KEYLIB until=2099-01-01 sharp=1\ncid2 KEYBATCH until=2099-01-01\n")
    assert pdf2epub.sharp_left("KEYBATCH") == 0  # batch pass: no AI reading
    assert pdf2epub.sharp_left("KEYLIB") == 1
    lay = list(layout)
    assert pdf2epub.sharp_pages(doc, lay, confs, "te", "KEYLIB", read) == 1
    assert lay[0][0] == words, "a confident page stays as Tesseract read it"
    assert lay[1][0] == good and lay[2][0] == words, "budget of 1 swaps only the first unsure page"
    assert calls == ["te"]
    assert pdf2epub.sharp_left("KEYLIB") == 0, "used pages count against the budget"

    # a model answer much shorter than the page is junk: keep Tesseract, charge nothing
    pdf2epub.SHELF_KEYS.write_text("cid1 KEYLIB2 until=2099-01-01 sharp=10\n")
    lay = list(layout)
    assert pdf2epub.sharp_pages(doc, lay, confs, "te", "KEYLIB2", lambda i, l: "too short") == 0
    assert lay == layout and pdf2epub.sharp_left("KEYLIB2") == 10

    # the shelf key still unlocks paid limits (until= honoured with sharp= on the line)
    from starlette.requests import Request
    r = Request({"type": "http", "query_string": b"k=KEYLIB2", "headers": []})
    assert pdf2epub.shelf_key(r) == "KEYLIB2"
    print("ok")


if __name__ == "__main__":
    main()
