"""Self-check: a scanned book that carries a little real text (a "Downloaded from" footer, a
library stamp, a filled form field) still counts as scanned, so OCR reads it. Before this,
any text at all skipped OCR and the EPUB came out empty (reddit, 11-05: a filled PDF form
gave only the field's value).
Run: python3 test_stamped_scan.py"""
import pymupdf
from app import _mostly_scanned

BODY = "It was a bright cold day in April, and the clocks were striking thirteen. " * 30


def page_png() -> bytes:
    p = pymupdf.open().new_page()
    p.insert_textbox(pymupdf.Rect(72, 72, 520, 760), BODY, fontsize=12)
    return p.get_pixmap(dpi=100).tobytes("png")


def scan(n, stamp=None, field=False):
    png, doc = page_png(), pymupdf.open()
    for i in range(n):
        pg = doc.new_page()
        pg.insert_image(pg.rect, stream=png)
        if stamp and (stamp != "first" or i == 0):
            pg.insert_text((250, 820), "Downloaded from somelibrary.org", fontsize=7)
        if field and i == 0:
            w = pymupdf.Widget()
            w.field_type, w.field_name = pymupdf.PDF_WIDGET_TYPE_TEXT, "name"
            w.rect, w.field_value = pymupdf.Rect(170, 316, 500, 336), "Jane Doe"
            pg.add_widget(w)
    return pymupdf.open(stream=doc.tobytes(), filetype="pdf")


def born_digital(n, photo_every=0):
    png, doc = page_png(), pymupdf.open()
    for i in range(n):
        pg = doc.new_page()
        if photo_every and i % photo_every == 0:
            pg.insert_image(pymupdf.Rect(36, 36, 560, 700), stream=png)  # full-page plate
            pg.insert_text((72, 740), "Plate 3. The harbour at dawn.", fontsize=9)
        else:
            pg.insert_textbox(pymupdf.Rect(72, 72, 520, 760), BODY, fontsize=12)
    return pymupdf.open(stream=doc.tobytes(), filetype="pdf")


def main():
    assert _mostly_scanned(scan(4, stamp="all")), "footer stamp on every page hid the scan"
    assert _mostly_scanned(scan(4, stamp="first")), "stamp on page 1 hid the scan"
    assert _mostly_scanned(scan(1, field=True)), "filled form field hid the scanned form"
    assert not _mostly_scanned(born_digital(6)), "born-digital book sent to OCR"
    assert not _mostly_scanned(born_digital(6, photo_every=3)), "book with plates sent to OCR"
    print("ok: stamped scans go to OCR, born-digital books do not")


if __name__ == "__main__":
    main()
