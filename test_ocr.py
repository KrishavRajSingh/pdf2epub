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


def heads_with_misread_numbers():
    """11-10 Telugu novel: "మాయ 77" headers whose page number OCR misread as letters stayed in."""
    from app import ocr_chapters
    body = "ఒక చిన్న గ్రామంలో ఒక రైతు ఉండేవాడు. అతను ప్రతి రోజు పొలానికి వెళ్ళేవాడు."
    nums = ["7", "డే", "ర్\u200c1", "9", "క్\u200c", "11", "డ9", "13"]
    pages = [f"మాయ {n}\n\n{body} {i}" for i, n in enumerate(nums)]
    text = " ".join(t for ch in ocr_chapters(pages) for k, t in ch)
    assert "మాయ" not in text, text[:200]
    assert text.count("గ్రామంలో") == len(nums), "body text was dropped with the headers"
    # a short line that only starts some pages is dialogue, not a header
    talk = [f"“అంటే?” అన్నాడు\n\n{body}" if i % 4 == 0 else body for i in range(8)]
    assert "అంటే" in " ".join(t for ch in ocr_chapters(talk) for k, t in ch), "dialogue dropped as a header"
    print("ok — misread running heads dropped")


def clean_layer_page_kept():
    """A real-text page (English copyright page) in an OCR'd book keeps its own text."""
    from app import _clean_layer
    d = pymupdf.open()
    d.new_page().insert_textbox(pymupdf.Rect(72, 72, 520, 400),
        "SURYADEVARA RAM MOHANA RAO\nPublished by Test Press, Hyderabad 500 096\nFirst edition 2019", fontsize=12)
    got = _clean_layer(d[0])
    assert got and "Test Press" in got[0], got
    img = pymupdf.open()  # a scan page with a stamp keeps going to OCR
    pg = img.new_page()
    pg.insert_image(pg.rect, stream=d[0].get_pixmap(dpi=72).tobytes("png"))
    pg.insert_text((72, 820), "Downloaded from somelibrary.org on 2026-11-10 by a reader", fontsize=7)
    assert _clean_layer(pg) is None, "a scanned page with a stamp skipped OCR"
    print("ok — clean text pages keep their layer")


def mixed_page_second_pass():
    """A page printed half in English inside a Telugu book (cover, web links) read with the
    Telugu model alone came out as "111౮1 & 4018010" junk (11-10)."""
    css = ('@font-face {font-family: tel; src: url("Telugu MN.ttc");} body {font-family: tel; font-size: 15px;}')
    src = pymupdf.open().new_page()
    src.insert_text((72, 90), "For My eBooks : www.example.com", fontsize=16)
    src.insert_text((72, 120), "For My Web Magazine Serials : www.gotelugu.com", fontsize=16)
    src.insert_htmlbox(pymupdf.Rect(72, 160, 520, 400), "<p>ఒక చిన్న గ్రామంలో ఒక రైతు ఉండేవాడు.</p>",
                       css=css, archive=pymupdf.Archive("/System/Library/Fonts/Supplemental"))
    d = pymupdf.open()
    pg = d.new_page()
    pg.insert_image(pg.rect, stream=src.get_pixmap(dpi=150).tobytes("png"))
    text = ocr_doc(d, lang="tel")[0]
    assert "www.example.com" in text and "గ్రామంలో" in text, text
    print("ok — mixed English/Telugu page reads both")


if __name__ == "__main__":
    main()
    heads_with_misread_numbers()
    clean_layer_page_kept()
    mixed_page_second_pass()
