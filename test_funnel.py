"""Check the text path: paragraphs stay paragraphs, headers/page numbers go, chapters appear.

Run: python3 test_funnel.py
"""
import os, re, tempfile, zipfile
from pathlib import Path

os.environ["LOG_DIR"] = tempfile.mkdtemp()  # keep the real conversions.log clean
import pymupdf
from fastapi.testclient import TestClient
import app as pdf2epub


def make_pdf() -> bytes:
    doc = pymupdf.open()
    body = ("This is a sample PDF so you can try the converter without hunting for a file. "
            "If this comes out as one clean paragraph in your reader, the converter joined the "
            "printed lines back together and dropped the running header.")
    for i, head in enumerate(["Chapter One", "Chapter Two"]):
        page = doc.new_page()
        page.insert_text((72, 60), "Sample Book - a running header", fontsize=9)
        page.insert_text((72, 120), head, fontsize=22)
        page.insert_textbox(pymupdf.Rect(72, 150, 520, 420), body, fontsize=11)
        page.insert_text((300, 780), str(i + 1), fontsize=9)
    raw = doc.tobytes()
    doc.close()
    return raw


def main():
    client = TestClient(pdf2epub.app)
    r = client.post("/convert", files={"f": ("sample.pdf", make_pdf(), "application/pdf")},
                    data={"title": "Sample Book", "email": "t@example.com"})
    assert r.status_code == 200, (r.status_code, r.text[:200])
    z = zipfile.ZipFile(__import__("io").BytesIO(r.content))
    html = "".join(z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.endswith(".xhtml"))

    assert "<h1>Chapter One</h1>" in html, "chapter heading missing"
    assert "<h1>Chapter Two</h1>" in html, "second chapter heading missing"
    assert "Sample Book - a running header" not in html, "running header was not stripped"
    assert not re.search(r"<p>\s*1\s*</p>", html), "page number was not stripped"

    nav = "".join(z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.endswith("nav.xhtml"))
    assert "Chapter One" in nav and "Chapter Two" in nav, "TOC labels are not the chapter names"

    paras = re.findall(r"<p>(.*?)</p>", html, re.S)
    assert len(paras) == 2, f"expected 2 paragraphs (one per chapter), got {len(paras)}"
    assert "sample PDF so you can try the converter" in paras[0], "paragraph text not joined"

    # phone scan -> OCR -> epub
    img = pymupdf.open()
    pg = img.new_page(width=1240, height=1754)
    pg.insert_text((100, 200), "Chapter 1", fontsize=44)
    pg.insert_text((100, 300), "The quick brown fox jumps over the lazy dog.", fontsize=32)
    png = img[0].get_pixmap(dpi=150).tobytes("png")
    r = client.post("/scan", files=[("files", ("p1.png", png, "image/png"))], data={"title": "Scan"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    z2 = zipfile.ZipFile(__import__("io").BytesIO(r.content))
    h2 = "".join(z2.read(n).decode("utf-8", "replace") for n in z2.namelist() if n.endswith(".xhtml"))
    assert "Chapter 1" in h2, f"scan heading missing: {h2[:300]}"
    assert "quick brown fox" in h2.lower(), "scan text missing"

    # guide pages + sitemap
    for u in ["/scan", "/guides", "/guides/pdf-to-epub", "/sitemap.xml"]:
        assert client.get(u).status_code == 200, u

    # email capture + sample endpoint
    st = client.get("/stats").json()
    assert st["emails_captured"] == 1, st
    s = client.get("/sample.pdf")
    assert s.status_code == 200 and s.content[:4] == b"%PDF", "sample.pdf broken"

    # the money path: a shelf page to point at, a live checkout link in it, and a
    # lead captured at the moment the free converter refuses a big file
    shelf = client.get("/shelf")
    assert shelf.status_code == 200, "no /shelf page to point people at"
    assert "buy.polar.sh" in shelf.text, "shelf page has no checkout link"
    land = client.get("/").text
    assert "/shelf" in land, "landing page does not mention the paid tier"
    assert client.post("/lead", data={"email": "", "reason": "cap"}).status_code == 400, "lead takes no email"
    assert client.post("/lead", data={"email": "r@e.com", "reason": "cap"}).status_code == 200
    st2 = client.get("/stats").json()
    assert st2["leads"] == 1, st2
    client.get("/thanks?checkout_id=polar_c_TEST")
    assert client.get("/stats").json()["checkouts"] == 1, "checkout not counted"

    # control chars in the PDF text must not 500 (lxml refuses them in XML)
    ctrl = pymupdf.open()
    cp = ctrl.new_page()
    cp.insert_text((72, 100), "Chapter\x0cOne", fontsize=22)
    cp.insert_text((72, 140), "Body text here.", fontsize=12)
    craw = ctrl.tobytes()
    ctrl.close()
    r2 = client.post("/convert", files={"f": ("c.pdf", craw, "application/pdf")},
                     data={"title": "Ti\x07tle"})
    assert r2.status_code == 200, (r2.status_code, r2.text[:200])

    # the ?s= tag must survive the landing page -> convert POST, else no channel is measurable
    client.get("/?s=post-ereader")
    client.post("/convert", files={"f": ("c.pdf", craw, "application/pdf")},
                headers={"referer": "https://epub.ftak.net/?s=post-ereader"})
    assert client.get("/stats").json()["ok_by_ref"].get("post-ereader"), "ref tag lost"

    # throttle must key on the real client ip, not the rotating railway proxy ip.
    # the limit is 30/min: the real shelf owner did 9/min peak, 68 in 32 minutes,
    # so the cap must not fire below that or it kills the revenue event.
    codes = [client.post("/convert", files={"f": ("c.pdf", craw, "application/pdf")},
                         headers={"x-forwarded-for": "203.0.113.9"}).status_code for _ in range(35)]
    assert 429 in codes, f"throttle never fired: {codes}"
    assert codes[:30].count(200) == 30, f"throttle cut a legitimate burst too early: {codes}"

    # the paid tier: a key from a real checkout lifts the per-file ceiling, a junk one does not
    big = pymupdf.open()
    for i in range(600):  # over the 500-page free cap, under the 2000-page paid cap
        big.new_page().insert_text((72, 100), f"page {i}", fontsize=11)
    braw = big.tobytes()
    big.close()

    def convert_with(q):
        return client.post("/convert" + q, files={"f": ("b.pdf", braw, "application/pdf")}).status_code

    assert convert_with("") == 413, "free tier should stop a 600 page pdf"
    assert convert_with("?k=not-a-real-key") == 413, "a junk key must not lift the cap"
    junk = client.get("/thanks?checkout_id=nonsense").text
    assert "Shelf key" not in junk, "a junk checkout id must not mint a key"
    cid = "polar_c_OKg9x4z0oQeMJ1zTeKMr1UAhmb5VGlVV74Byn0xg8y8"
    page = client.get(f"/thanks?checkout_id={cid}").text
    assert "Shelf key" in page, "a real checkout id must mint a key"
    key = re.search(r"\?k=([0-9A-Za-z_-]+)</code>", page).group(1)
    assert convert_with(f"?k={key}") == 200, "a paid key must lift the 500 page cap"
    # same checkout must not mint a second key on a page refresh
    again = client.get(f"/thanks?checkout_id={cid}").text
    assert re.search(r"\?k=([0-9A-Za-z_-]+)</code>", again).group(1) == key, "key changed on refresh"

    print("ok: paragraphs joined, header+page number stripped, 2 chapters, email captured, sample.pdf serves, paid key lifts the cap")


if __name__ == "__main__":
    main()
