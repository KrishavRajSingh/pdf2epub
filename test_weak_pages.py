"""Scanned books end with a "Pages to check" chapter listing pages the OCR stayed unsure of.

Run: python3 test_weak_pages.py
"""
import io, os, tempfile, zipfile

os.environ["LOG_DIR"] = tempfile.mkdtemp()
import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import app as a


def scan_pdf(blur_pages: set, n: int = 3) -> bytes:
    """n image-only pages of prose; pages in blur_pages are blurred and shrunk so OCR struggles."""
    text = ("It was late in the evening when the old ferryman finally pushed away from the bank, and the "
            "river was wide and slow under a pale sky. ") * 3
    doc = pymupdf.open()
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Times New Roman.ttf", 34)
    except OSError:
        font = ImageFont.load_default()
    for p in range(n):
        im = Image.new("L", (1240, 1754), 255)
        d = ImageDraw.Draw(im)
        words, line, y = text.split(), "", 120
        for w in words:
            if d.textlength(line + " " + w, font=font) > 1000:
                d.text((120, y), line, font=font, fill=0); y += 52; line = w
            else:
                line = (line + " " + w).strip()
        d.text((120, y), line, font=font, fill=0)
        if p in blur_pages:
            im = im.resize((310, 438)).filter(ImageFilter.GaussianBlur(1.2)).resize((1240, 1754))
        buf = io.BytesIO(); im.save(buf, "PNG")
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=buf.getvalue())
    raw = doc.tobytes(); doc.close()
    return raw


def main():
    # unit: only unsure text pages are listed, 1-based; pictures (few words) are not
    layout = [("word " * 50, 0), ("word " * 50, 0), ("pic", 0), ("word " * 50, 0)]
    assert a.weak_pages(layout, {0: 95.0, 1: 40.0, 2: 0.0, 3: 69.9}) == [2, 4]
    ch = a.check_chapter([2, 4], 4)
    assert ch[0] == ("h1", "Pages to check") and ch[2] == ("p", "2, 4"), ch
    assert a.check_chapter([], 4) == []
    assert "and 5 more" in a.check_chapter(list(range(1, 66)), 70)[2][1]

    # end to end: a scan with one bad page lists that page, a clean scan lists nothing
    if not a.shutil.which("tesseract"):
        print("ok weak_pages (unit only, no tesseract)"); return
    from fastapi.testclient import TestClient
    c = TestClient(a.app)
    hdr = {"user-agent": "Mozilla/5.0 (Macintosh) Safari/605"}
    def chapters_of(raw):
        r = c.post("/convert", files={"f": ("scan.pdf", raw, "application/pdf")}, data={"title": "t", "author": ""}, headers=hdr)
        assert r.status_code == 200, r.text[:200]
        z = zipfile.ZipFile(io.BytesIO(r.content))
        return " ".join(z.read(n).decode("utf8", "ignore") for n in z.namelist() if n.endswith((".xhtml", ".html")))
    bad = chapters_of(scan_pdf({1}))
    assert "Pages to check" in bad, "blurred page not listed"
    good = chapters_of(scan_pdf(set()))
    assert "Pages to check" not in good, "clean scan should list nothing"
    land = c.get("/").text
    assert "listed at the end of your book" in land
    print("ok weak_pages")


if __name__ == "__main__":
    main()
