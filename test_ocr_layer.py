"""Self-check: an invisible OCR text layer (Internet Archive scans) that cuts paragraphs into
blocks mid-sentence comes out as whole paragraphs, without "[7]" page numbers.
Run: python3 test_ocr_layer.py"""
import pymupdf
from app import _blocks, _ocr_layer, _structure


def make_pdf() -> bytes:
    doc = pymupdf.open()
    lines = [  # (y, size, text): blocks 40pt apart, as the IA layer splits them
        (60, 11, "Chapter I"),
        (120, 11, "The boy rode out early that spring morning across the hills and"),
        (160, 14, "down to the river, where the willows grew thick along the bank."),
        (200, 11, "He sat by the water for a long time and watched the far side of the horse-"),
        (240, 11, "shoe bend until the sun was high."),
        (280, 11, "[7]"),
    ]
    for page in range(2):
        p = doc.new_page(width=330, height=520)
        for y, size, text in lines:
            p.insert_text((24, y), text, fontsize=size * 0.6, render_mode=3)
    return doc.tobytes()


def main():
    doc = pymupdf.open(stream=make_pdf(), filetype="pdf")
    assert _ocr_layer(doc), "invisible text layer not detected"
    chapters = _structure(list(_blocks(doc)), doc)
    paras = [t for ch in chapters for k, t in ch if k == "p"]
    assert all("[7]" not in t for t in paras), f"page number left in: {paras}"
    assert paras[0].startswith("The boy") and paras[0].endswith("bank."), paras
    assert "horseshoe bend" in paras[1], f"hyphen across blocks not joined: {paras}"
    assert not [t for ch in chapters for k, t in ch if k == "h2"], "big OCR line became a heading"
    print("ok: OCR-layer blocks joined into paragraphs, page numbers dropped, no fake headings")


if __name__ == "__main__":
    main()
