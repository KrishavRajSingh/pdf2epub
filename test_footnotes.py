"""Self-check: page-bottom footnote blocks move to chapter end, markers keep their raise.
Run: python3 test_footnotes.py"""
import io
import zipfile
import pymupdf
from app import _blocks, _figure_rect, _page_rect, _structure, _span_text, build_epub, CAPTION_RE


def make_pdf() -> bytes:
    doc = pymupdf.open()
    p = doc.new_page(width=612, height=792)
    p.insert_text((72, 20), "1 Test Book", fontsize=9)  # running head, differs per page
    p.insert_text((72, 72), "Chapter 1", fontsize=11)  # body-font heading, the Palmer case
    for y in range(110, 620, 20):
        p.insert_text((72, y), "This is body prose that belongs in the paragraph flow of the chapter.",
                      fontsize=11)
    p.insert_text((72, 700), "1 A footnote about the sources and the method used here.",
                  fontsize=8)
    p.insert_text((72, 716), "2 Another note, second in the page order.", fontsize=8)
    p.insert_text((72, 770), "terms of use, available at https:/www.cambridge.org/core/terms. "
                  "Downloaded from https:/www.cambridge.org/core. University, on 14 Apr 2020.",
                  fontsize=6)
    q = doc.new_page()  # second page: a footer seen once is not a repeated running head
    q.insert_text((72, 20), "2 Test Book", fontsize=9)
    for i in range(8):
        q.draw_line((72, 120 + i * 25), (372, 120 + i * 25))
        q.draw_line((72 + i * 43, 120), (72 + i * 43, 320))
    q.insert_text((150, 220), "Map label inside figure", fontsize=6)
    q.insert_text((72, 340), "Map 1 A test map", fontsize=9)
    return doc.tobytes()


def main():
    assert _span_text({"text": "12", "flags": 1}) == "\u00b9\u00b2", "superscript marker not raised"
    assert _span_text({"text": "12", "flags": 0}) == "12", "plain digits must not change"
    assert CAPTION_RE.match("Map 3.3 A test map")
    assert CAPTION_RE.match("Fig. 4.1 A test chart")

    doc = pymupdf.open(stream=make_pdf(), filetype="pdf")
    chapters = _structure(list(_blocks(doc)), doc)
    ch = chapters[0]
    assert any(k == "h1" and t == "Chapter 1" for k, t in ch), "body-font heading lost"
    kinds = [k for k, _ in ch]
    notes = [t for k, t in ch if k == "fn"]
    assert len(notes) == 2, f"expected 2 notes, got {notes}"
    assert notes[0].startswith("1 A footnote"), notes
    text_kinds = [k for k in kinds if k != "img"]
    assert text_kinds[-2:] == ["fn", "fn"], f"notes not at chapter end: {kinds}"
    text = [(k, t) for k, t in ch if k != "img"]
    assert all("footnote about" not in t for k, t in text if k != "fn"), "note leaked into prose"
    assert all("Downloaded from" not in t for k, t in text), "publisher footer leaked into prose"
    assert all("Test Book" not in t for k, t in text), "running head leaked into prose"
    imgs = [t for k, t in ch if k == "img"]
    assert len(imgs) == 1 and imgs[0][0][:4] == b"\x89PNG", "figure not rasterised"
    assert imgs[0][1] == "Map 1 A test map", imgs[0][1]
    assert all("Map label inside figure" not in t for k, t in text), "map label leaked"
    assert all("Map 1 A test map" not in t for k, t in text), "map caption leaked"

    data = build_epub(chapters, "T", "A")
    assert data[:2] == b"PK", "not an epub zip"
    z = zipfile.ZipFile(io.BytesIO(data))
    assert any(n.endswith("fig1.png") for n in z.namelist()), "figure missing from epub"
    z.close()
    doc.close()
    check_rotated_figure()
    print("ok: 2 notes moved to chapter end, prose clean, figure rotation, epub built")


def check_rotated_figure():
    """Landscape map pages are rotated; the clip must use the full unrotated page box."""
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=600)
    for i in range(8):
        page.draw_line((40, 50 + i * 60), (200, 50 + i * 60))
        page.draw_line((40 + i * 23, 50), (40 + i * 23, 520))
    page.insert_text((220, 150), "Fig. 2 A rotated map", fontsize=9, rotate=90)
    page.set_rotation(90)
    fig = _figure_rect(page, page.get_text("dict")["blocks"], 10)
    assert fig and round(fig.y1) >= 520, f"rotated figure clipped: {fig}"
    pm = page.get_pixmap(clip=_page_rect(page, fig))
    assert pm.width > 450 and pm.height < 200, f"wrong rotated clip: {pm.width}x{pm.height}"
    blocks = list(_blocks(doc))
    imgs = [t for _, _, sz, t in blocks if sz < 0]
    assert len(imgs) == 1 and imgs[0][1] == "Fig. 2 A rotated map", imgs
    assert all("Fig. 2" not in t for _, _, sz, t in blocks if sz >= 0), "rotated caption leaked"
    doc.close()


if __name__ == "__main__":
    main()
