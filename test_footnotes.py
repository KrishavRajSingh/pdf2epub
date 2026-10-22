"""Self-check: page-bottom footnote blocks move to chapter end, markers keep their raise.
Run: python3 test_footnotes.py"""
import pymupdf
from app import _blocks, _structure, _span_text, build_epub


def make_pdf() -> bytes:
    doc = pymupdf.open()
    p = doc.new_page(width=612, height=792)
    p.insert_text((72, 72), "Chapter 1", fontsize=20)
    for y in range(110, 620, 20):
        p.insert_text((72, y), "This is body prose that belongs in the paragraph flow of the chapter.",
                      fontsize=11)
    p.insert_text((72, 700), "1 A footnote about the sources and the method used here.",
                  fontsize=8)
    p.insert_text((72, 716), "2 Another note, second in the page order.", fontsize=8)
    return doc.tobytes()


def main():
    assert _span_text({"text": "12", "flags": 1}) == "\u00b9\u00b2", "superscript marker not raised"
    assert _span_text({"text": "12", "flags": 0}) == "12", "plain digits must not change"

    doc = pymupdf.open(stream=make_pdf(), filetype="pdf")
    chapters = _structure(list(_blocks(doc)), doc)
    ch = chapters[0]
    kinds = [k for k, _ in ch]
    notes = [t for k, t in ch if k == "fn"]
    assert len(notes) == 2, f"expected 2 notes, got {notes}"
    assert notes[0].startswith("1 A footnote"), notes
    assert kinds.index("fn") == len(kinds) - 2, f"notes not at chapter end: {kinds}"
    assert all("footnote about" not in t for k, t in ch if k != "fn"), "note leaked into prose"

    data = build_epub(chapters, "T", "A")
    assert data[:2] == b"PK", "not an epub zip"
    doc.close()
    print("ok: 2 notes moved to chapter end, prose clean, epub built")


if __name__ == "__main__":
    main()
