"""Check the text path: paragraphs stay paragraphs, headers/page numbers go, chapters appear.

Run: python3 test_funnel.py
"""
import json, os, re, tempfile, zipfile
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
    from starlette.requests import Request

    def req(qs="", ref=""):
        return Request({"type": "http", "query_string": qs.encode(),
                        "headers": [(b"referer", ref.encode())]})

    assert pdf2epub.ref_of(req("", "https://epub.ftak.net/?utm_source=substack&utm_medium=email")) == \
        "substack|https://epub.ftak.net/?utm_source=substack&utm_medium=email"
    assert pdf2epub.ref_of(req("s=deepculture", "")) == "deepculture|"

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
    # /pt/ and /es/: same converter, translated copy, tied to the english page by hreflang
    for lang, word in (("pt", "Converter para EPUB"), ("es", "Convertir a EPUB")):
        pg = client.get(f"/{lang}/")
        assert pg.status_code == 200 and word in pg.text, f"/{lang}/ not translated"
        assert f'hreflang="{lang}"' in pg.text and 'hreflang="x-default"' in pg.text, f"/{lang}/ lacks hreflang"
        assert f'rel="canonical" href="https://epub.ftak.net/{lang}/"' in pg.text, f"/{lang}/ canonical wrong"
        for en in ("Convert to EPUB", "Drop a PDF here", "What it repairs", "Choose a PDF first"):
            assert en not in pg.text, f"/{lang}/ still has english: {en}"
        assert f"https://epub.ftak.net/{lang}/" in client.get("/sitemap.xml").text, f"/{lang}/ not in sitemap"
    assert 'rel="canonical" href="https://epub.ftak.net/"' in client.get("/").text, "english canonical missing"
    # indexnow: the engines fetch the key file to prove we own the host
    assert client.get(f"/{pdf2epub.INDEXNOW_KEY}.txt").text == pdf2epub.INDEXNOW_KEY, "indexnow key not served"

    # email capture + sample endpoint
    st = client.get("/stats").json()
    assert st["emails_captured"] == 1, st
    s = client.get("/sample.pdf")
    assert s.status_code == 200 and s.content[:4] == b"%PDF", "sample.pdf broken"

    # the money path: a shelf page to point at, a live checkout link in it, and a
    # lead captured at the moment the free converter refuses a big file
    shelf = client.get("/shelf")
    assert shelf.status_code == 200, "no /shelf page to point people at"
    assert "/go/shelf" in shelf.text, "shelf page has no checkout link"
    assert "/go/onebook" in shelf.text, "shelf page has no one-book link"
    assert "$5" in shelf.text and "on the spot" in shelf.text, \
        "shelf page does not pitch the $5 one-book job"
    # checkout links go through /go so the click is counted, then on to polar
    for offer, url in (("onebook", pdf2epub.ONETIME_URL), ("shelf", pdf2epub.SHELF_URL)):
        g = client.get(f"/go/{offer}?why=test", follow_redirects=False)
        assert g.status_code == 302 and g.headers["location"] == url, (offer, g.status_code)
    assert client.get("/go/nope", follow_redirects=False).status_code == 404
    assert "quote a one-time" not in shelf.text, "shelf still quotes a one-time conversion"
    land = client.get("/").text
    assert "/shelf" in land, "landing page does not mention the paid tier"
    assert client.post("/lead", data={"email": "", "reason": "cap"}).status_code == 400, "lead takes no email"
    assert client.post("/lead", data={"email": "r@e.com", "reason": "cap"}).status_code == 200
    st2 = client.get("/stats").json()
    assert st2["leads"] == 1, st2
    client.get("/thanks?checkout_id=polar_c_TEST")
    assert client.get("/stats").json()["checkouts"] == 1, "checkout not counted"
    one = client.get("/onebook?checkout_id=polar_c_ONETIME1234567890abcdef")
    assert one.status_code == 200 and "One book" in one.text and "Email the PDF" in one.text, \
        "one-book success page missing"
    assert "Shelf key" not in one.text, "one-book success page must not mint a shelf key"
    assert "Payment not confirmed" in one.text, "unverified one-book checkout looked paid"
    ocid = "a52e14f4-b1d8-4dbf-bb60-08f531923d3d"
    real_paid = pdf2epub.paid_checkout
    pdf2epub.paid_checkout = lambda c, p: (c, p) == (ocid, pdf2epub.ONEBOOK_PRODUCT)
    paid_one = client.get(f"/onebook?checkout_id={ocid}").text
    assert "Payment confirmed" in paid_one, "verified one-book checkout did not confirm"
    assert "Shelf key" not in paid_one, "one-book page must never mint a shelf key"
    pdf2epub.paid_checkout = real_paid
    assert client.get("/stats").json()["checkouts"] == 3, "one-book checkout not counted"

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
    cap = client.post("/convert", files={"f": ("b.pdf", braw, "application/pdf")},
                      headers={"accept": "text/html"})
    assert cap.status_code == 413 and "$5" in cap.text and "/go/onebook" in cap.text, \
        "cap rejection does not pitch the $5 one-book job"
    assert "quote a one-time conversion" not in cap.text, \
        "cap rejection still quotes instead of selling"
    # a long book can take its first 500 pages free, with a closing chapter that sells the rest
    pv = client.post("/convert", files={"f": ("b.pdf", braw, "application/pdf")}, data={"preview": "1"})
    assert pv.status_code == 200, pv.text[:200]
    zv = zipfile.ZipFile(__import__("io").BytesIO(pv.content))
    hv = "".join(zv.read(n).decode("utf-8", "replace") for n in zv.namelist() if n.endswith(".xhtml"))
    assert "page 499" in hv and "page 500" not in hv, "page preview is not the first 500 pages"
    assert "the first 500 of 600 pages" in hv, "page preview does not sell the rest"
    assert convert_with("?k=not-a-real-key") == 413, "a junk key must not lift the cap"
    junk = client.get("/thanks?checkout_id=nonsense").text
    assert "Shelf key" not in junk, "a junk checkout id must not mint a key"
    fake = client.get("/thanks?checkout_id=polar_c_AAAAAAAAAAAAAAAAAAAAAAAA").text
    assert "Shelf key" not in fake, "a fabricated polar_c id must not mint a key"
    # real polar checkout ids are uuids, and only polar may say a checkout succeeded
    cid = "69c101bb-0ede-4bb1-893f-cf4fd471aab4"
    assert "Shelf key" not in client.get(f"/thanks?checkout_id={cid}").text, \
        "unverified checkout minted a key"
    pdf2epub.paid_checkout = lambda c, p: (c, p) == (cid, pdf2epub.SHELF_PRODUCT)
    page = client.get(f"/thanks?checkout_id={cid}").text
    assert "Shelf key" in page, "a verified checkout must mint a key"
    key = re.search(r"\?k=([0-9A-Za-z_-]+)</code>", page).group(1)
    assert convert_with(f"?k={key}") == 200, "a paid key must lift the 500 page cap"
    # same checkout must not mint a second key on a page refresh
    again = client.get(f"/thanks?checkout_id={cid}").text
    assert re.search(r"\?k=([0-9A-Za-z_-]+)</code>", again).group(1) == key, "key changed on refresh"
    pdf2epub.paid_checkout = real_paid

    # the $5 one-book converts on the spot: a verified checkout lifts the cap for one file,
    # re-running that same file stays free, a second different book does not ride on it
    bcid = "0b5e3a52-7c1d-4e8f-9a6b-2d4c8e1f3a7b"
    pdf2epub.paid_checkout = lambda c, p: (c, p) == (bcid, pdf2epub.ONEBOOK_PRODUCT)
    assert convert_with(f"?paid={bcid}") == 200, "a paid one-book must lift the 500 page cap"
    assert convert_with(f"?paid={bcid}") == 200, "re-running the paid book must stay free"
    other = client.post(f"/convert?paid={bcid}", files={"f": ("c.pdf", craw, "application/pdf")})
    assert other.status_code == 402, "one payment converted a second, different book"
    assert convert_with("?paid=69c101bb-0ede-4bb1-893f-000000000000") == 402, "unpaid checkout lifted the cap"
    pdf2epub.paid_checkout = real_paid

    # the OCR wall: a short scan is free, a long scan is refused with a $5 offer, the preview
    # reads the first free pages, and a paid checkout reads the whole book
    def make_scan(n):
        src = pymupdf.open()
        out = pymupdf.open()
        for i in range(n):
            p = src.new_page(width=1240, height=1754)
            p.insert_text((100, 200), f"Chapter {i + 1}", fontsize=44)
            p.insert_text((100, 300), "The quick brown fox jumps over the lazy dog again.", fontsize=32)
            p.insert_text((100, 400), "A second line of printed text for the OCR to read.", fontsize=32)
            pg = out.new_page(width=1240, height=1754)
            pg.insert_image(pg.rect, stream=src[i].get_pixmap(dpi=150).tobytes("png"))
        return out.tobytes()

    pdf2epub.FREE_OCR_PAGES = 2  # ponytail: 20 real OCR pages is a minute of test time
    sraw = make_scan(4)
    scan = lambda q="", d=None: client.post("/convert" + q, files={"f": ("s.pdf", sraw, "application/pdf")},
                                            data=d or {}, headers={"x-v": "testvisitor1"})
    wall = scan()
    assert wall.status_code == 402 and "scanned" in wall.text and "(4 here)" in wall.text, wall.text[:200]
    prev = scan(d={"preview": "1"})
    assert prev.status_code == 200, prev.text[:200]
    zp = zipfile.ZipFile(__import__("io").BytesIO(prev.content))
    hp = "".join(zp.read(n).decode("utf-8", "replace") for n in zp.namelist() if n.endswith(".xhtml"))
    assert "The rest of this book" in hp and "Chapter 2" in hp and "Chapter 4" not in hp, "preview is not the first pages"
    short = client.post("/convert", files={"f": ("s.pdf", make_scan(2), "application/pdf")})
    assert short.status_code == 200, "a scan under the free OCR pages must stay free"
    scid = "7d2f1e4a-3b6c-4d8e-9f0a-1c2b3d4e5f6a"
    pdf2epub.paid_checkout = lambda c, p: (c, p) == (scid, pdf2epub.ONEBOOK_PRODUCT)
    full = scan(f"?paid={scid}")
    assert full.status_code == 200, full.text[:200]
    zf = zipfile.ZipFile(__import__("io").BytesIO(full.content))
    hf = "".join(zf.read(n).decode("utf-8", "replace") for n in zf.namelist() if n.endswith(".xhtml"))
    assert "Chapter 4" in hf and "The rest of this book" not in hf, "paid scan did not read every page"
    pdf2epub.paid_checkout = real_paid
    pdf2epub.FREE_OCR_PAGES = 20

    # the funnel: private, counts people by the page's random id, and attributes them to a source
    assert client.get("/funnel").status_code == 404, "funnel must be private without a key"
    pdf2epub.FUNNEL_KEY = "fk"
    v0 = client.get("/stats").json()["visits"]
    assert client.get("/funnel?k=wrong").status_code == 404
    hdr = {"user-agent": "Mozilla/5.0 (Macintosh) Safari/605"}
    for n in ("view", "pick", "submit", "pitch"):
        client.post("/e", content=json.dumps({"n": n, "v": "testvisitor1", "src": "reddit", "why": "ocr"}), headers=hdr)
    client.post("/e", content=json.dumps({"n": "view", "v": "x"}), headers=hdr)  # bad id, dropped
    client.post("/e", content=json.dumps({"n": "evil", "v": "testvisitor2"}), headers=hdr)  # unknown, dropped
    client.get("/go/onebook?why=ocr&v=testvisitor1", headers=hdr, follow_redirects=False)
    fj = client.get("/funnel?k=fk&format=json").json()
    row = {r["source"]: r for r in fj["rows"]}["reddit"]
    assert (row["view"], row["pick"], row["submit"], row["pitch"], row["click"]) == (1, 1, 1, 1, 1), row
    assert row["wall"] == 1 and row["converted"] == 1 and row["paid_convert"] == 1, row
    assert row["paid"] == 1, "a paid conversion must count as paid"
    assert "ocr-wall" in fj["errors"], fj["errors"]
    assert client.get("/funnel?k=fk").status_code == 200, "funnel html broken"
    assert client.get("/stats").json()["visits"] == v0, "beacons leaked into /stats"
    pdf2epub.FUNNEL_KEY = ""

    # the fulfilment email is the highest intent email in the system and it runs on the mac,
    # not on railway. it must point at a link that works and it must not crash.
    import importlib.util
    spec = importlib.util.spec_from_file_location("fulfil", Path(__file__).parent / "scripts" / "fulfil.py")
    fulfil = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fulfil)
    assert fulfil.pdf2epub.SHELF_URL in fulfil.pdf2epub.SHELF_URL, "no checkout url"
    epub, was_ocr = fulfil.convert(make_pdf(), "Test Book")
    assert len(epub) > 0 and was_ocr is False, (len(epub), was_ocr)
    # a scanned pdf must report that it was OCR'd, so the email can warn about the typos
    src = pymupdf.open()
    for i in range(2):
        p = src.new_page(width=1240, height=1754)
        p.insert_text((100, 200), f"Scanned chapter {i}", fontsize=44)
    imgpdf = pymupdf.open()
    for i in range(2):
        pix = src[i].get_pixmap(dpi=150)
        pg = imgpdf.new_page(width=1240, height=1754)
        pg.insert_image(pg.rect, stream=pix.tobytes("png"))
    epub2, was_ocr2 = fulfil.convert(imgpdf.tobytes(), "Scanned Book")
    assert was_ocr2 is True, "a scanned pdf must be reported as OCR"

    print("ok: paragraphs joined, header+page number stripped, 2 chapters, email captured, sample.pdf serves, paid key lifts the cap, fulfilment email ok")


if __name__ == "__main__":
    main()
