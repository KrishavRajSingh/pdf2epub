"""Self-check: synthetic scan PDF (image only, no text layer) -> OCR path -> epub with chapters and maps.
Run: python3 test_ocr.py"""
import io
import zipfile
import pymupdf
from app import ocr_doc, ocr_chapters, build_epub, _blocks, _scan_figures


def make_scan() -> bytes:
    src = pymupdf.open()
    p = src.new_page(width=612, height=792)
    p.insert_text((72, 100), "Chapter 1", fontsize=24)
    for i in range(22):
        p.insert_text((72, 140 + i * 20),
                      "The quick brown fox jumps over the lazy dog.", fontsize=12)

    m = src.new_page(width=612, height=792)
    for i in range(8):
        m.draw_line((72, 120 + i * 60), (372, 120 + i * 60))
        m.draw_line((72 + i * 43, 120), (72 + i * 43, 540))
    m.insert_text((150, 220), "Map label inside figure", fontsize=6)
    m.insert_text((72, 600), "Map 1 A test map", fontsize=9)

    q = src.new_page(width=612, height=792)
    q.insert_text((72, 100), "Chapter 2", fontsize=24)
    for i in range(10):
        q.insert_text((72, 140 + i * 20),
                      "The quick brown fox jumps over the lazy dog.", fontsize=12)

    scan = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=300)
        sp = scan.new_page(width=page.rect.width, height=page.rect.height)
        sp.insert_image(sp.rect, stream=pix.tobytes("png"))
    return scan.tobytes()


def main():
    doc = pymupdf.open(stream=make_scan(), filetype="pdf")
    assert not list(_blocks(doc)), "fake scan must have no text layer"

    pages = ocr_doc(doc, layout=True)
    assert pages, "tesseract missing"
    texts = [t for t, _ in pages]
    text = "\n".join(texts)
    assert "quick brown fox" in text.lower(), f"OCR text bad: {text[:200]}"

    figs = _scan_figures(doc, pages)
    assert len(figs) == 1, f"expected one map page, got {[(len(t), round(c, 3)) for t, c in pages]}"

    chapters = ocr_chapters(texts, figs)
    heads = [t for ch in chapters for k, t in ch if k == "h1"]
    assert any("chapter 1" in h.lower() for h in heads), f"no chapter 1: {chapters}"
    assert any("chapter 2" in h.lower() for h in heads), f"no chapter 2: {chapters}"
    imgs = [t for ch in chapters for k, t in ch if k == "img"]
    assert len(imgs) == 1 and imgs[0][0][:4] == b"\x89PNG", "scan map not rasterised"
    assert all("Map 1" not in t and "Map label" not in t
               for ch in chapters for k, t in ch if k != "img"), "map text leaked into prose"

    data = build_epub(chapters, "t", "a")
    assert data[:2] == b"PK", "not an epub zip"
    z = zipfile.ZipFile(io.BytesIO(data))
    assert any(n.endswith("fig1.png") for n in z.namelist()), "map missing from epub"
    z.close()
    doc.close()
    print("ok — headings:", heads, "figures:", len(imgs))


if __name__ == "__main__":
    main()
