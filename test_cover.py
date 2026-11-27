"""text_cover: page 1 of a text PDF is the shelf cover only when it looks like one.

Jon 11-26, Dark Continents: page 1 is a half-title, "A John Hope Franklin Center Book" in body type,
no picture; it went out as a white cover.jpg (epub_lint BLANK). A missing cover lets the reader draw
its own tile with the title; a white one shows nothing.
"""
import pymupdf

from app import text_cover, cover_title_author


def book(first):
    d = pymupdf.open()
    first(d.new_page(width=432, height=666))
    for k in range(25):
        d.new_page(width=432, height=666).insert_textbox(
            pymupdf.Rect(60, 60, 372, 600), f"Page {k}. " + "It was a bright cold day in April, and the clocks "
            "were striking thirteen. Winston Smith slipped quickly through the glass doors. " * 3, fontsize=10.5)
    return pymupdf.open(stream=d.tobytes(), filetype="pdf")


def half_title(pg):
    pg.insert_text((150, 120), "A John Hope Franklin Center Book", fontsize=10.5)


def typeset_cover(pg):
    pg.insert_text((60, 200), "Dark Continents", fontsize=30)
    pg.insert_text((60, 260), "Ranjana Khanna", fontsize=16)


def picture_cover(pg):
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 60), 0)
    pix.set_rect(pix.irect, (200, 80, 40))
    pg.insert_image(pg.rect, pixmap=pix)


def tiled_cover(pg):  # te-loya (corpus): a cover cut into 10 strips, none 40% of the page
    for k in range(10):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 6), 0)
        pix.set_rect(pix.irect, (40 + k * 20, 90, 160))
        pg.insert_image(pymupdf.Rect(0, k * 66.6, 432, (k + 1) * 66.6), pixmap=pix)


assert text_cover(book(half_title)) is None, "half-title in body type is no cover"
assert text_cover(book(typeset_cover)), "a typeset cover (title in display type) is kept"
assert text_cover(book(picture_cover)), "a picture cover is kept"
assert text_cover(book(tiled_cover)), "a cover made of strips is kept"

def press_front(pg):  # Dark Continents: half-title, series page, title page, all in body type
    pg.insert_text((150, 120), "A John Hope Franklin Center Book", fontsize=10.5)


d = book(press_front)
d2 = pymupdf.open()
d2.insert_pdf(d, to_page=0)
d2.new_page(width=432, height=666).insert_text((150, 120), "Post-Contemporary\nInterventions\nSeries Editors:", fontsize=10.5)
d2.insert_pdf(d, from_page=1)
d2 = pymupdf.open(stream=d2.tobytes(), filetype="pdf")
assert cover_title_author(d2) == ("", ""), cover_title_author(d2)
assert cover_title_author(book(typeset_cover)) == ("Dark Continents", "Ranjana Khanna"), cover_title_author(book(typeset_cover))
print("ok: text_cover, title guess")
