"""Self-check: synthetic scan PDF (image only, no text layer) -> OCR path -> epub with chapters.
Run: python3 test_ocr.py"""
import pymupdf
from app import ocr_doc, ocr_chapters, build_epub, _blocks


def make_scan() -> bytes:
    src = pymupdf.open()
    p = src.new_page()
    p.insert_text((72, 100), "Chapter 1", fontsize=24)
    p.insert_text((72, 140), "The quick brown fox jumps over the lazy dog.", fontsize=12)
    pix = p.get_pixmap(dpi=300)
    scan = pymupdf.open()
    sp = scan.new_page(width=src[0].rect.width, height=src[0].rect.height)
    sp.insert_image(sp.rect, stream=pix.tobytes("png"))
    return scan.tobytes()


def main():
    doc = pymupdf.open(stream=make_scan(), filetype="pdf")
    assert not list(_blocks(doc)), "fake scan must have no text layer"
    pages = ocr_doc(doc)
    assert pages, "tesseract missing"
    text = "\n".join(pages)
    assert "quick brown fox" in text.lower(), f"OCR text bad: {text[:200]}"
    chapters = ocr_chapters(pages)
    heads = [t for k, t in chapters[0] if k == "h1"]
    assert any("chapter 1" in h.lower() for h in heads), f"no heading found: {chapters}"
    data = build_epub(chapters, "t", "a")
    assert data[:2] == b"PK", "not an epub zip"
    print("ok — heading:", heads[0])


if __name__ == "__main__":
    main()
