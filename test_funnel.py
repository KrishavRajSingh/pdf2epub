"""Check the text path: paragraphs stay paragraphs, headers/page numbers go, chapters appear.

Run: python3 test_funnel.py
"""
import json, os, re, tempfile, time, zipfile
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
    # 11-10: GSC "crawled - not indexed" on every guide. Scan guide = converter link first + FAQ JSON-LD,
    # home links each guide directly, /stats is noindex.
    g = client.get("/guides/scanned-pdf-to-epub")
    assert g.status_code == 200 and '"@type": "FAQPage"' in g.text and 'href="/?s=seo-scan"' in g.text, "scan guide"
    assert "<h1>Scanned PDF to EPUB</h1>" in g.text, "scan guide h1"
    assert client.get("/guides/pdf-to-epub").status_code == 200, "plain guide (no faq) broke"
    home = client.get("/").text
    for slug in ("scanned-pdf-to-epub", "send-pdf-to-kindle", "pdf-to-epub-vs-calibre"):
        assert f'href="/guides/{slug}"' in home, f"home lacks link to {slug}"
    assert client.get("/stats").headers.get("x-robots-tag") == "noindex", "/stats indexable"
    # 11-11: comparison page for AI answers: FAQ + ItemList JSON-LD, dated, in sitemap and /guides
    c = client.get("/guides/pdf-to-epub-converters-compared")
    assert c.status_code == 200 and '"@type": "FAQPage"' in c.text and '"@type":"ItemList"' in c.text, "compare page"
    assert "Checked 11 November 2026" in c.text and 'href="/?s=seo-compare"' in c.text, "compare page date/cta"
    assert "/guides/pdf-to-epub-converters-compared" in client.get("/sitemap.xml").text, "compare page not in sitemap"
    assert 'href="/guides/pdf-to-epub-converters-compared"' in client.get("/guides").text, "compare page not in /guides"

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
    for offer, url in (("onebook", pdf2epub.ONETIME_URL), ("short", pdf2epub.SHORT_URL), ("shelf", pdf2epub.SHELF_URL)):
        g = client.get(f"/go/{offer}?why=test", follow_redirects=False)
        assert g.status_code == 302 and g.headers["location"] == url, (offer, g.status_code)
    assert client.get("/go/nope", follow_redirects=False).status_code == 404
    assert "quote a one-time" not in shelf.text, "shelf still quotes a one-time conversion"
    land = client.get("/").text
    # Shelf batch upload (11-10): many PDFs or a folder, one job each
    assert "convertMany" in land and "webkitdirectory" in land and "if(K){fi.multiple=true" in land, "no batch upload"
    assert "/shelf" in land, "landing page does not mention the paid tier"
    assert client.post("/lead", data={"email": "", "reason": "cap"}).status_code == 400, "lead takes no email"
    assert client.post("/lead", data={"email": "r@e.com", "reason": "cap"}).status_code == 200
    st2 = client.get("/stats").json()
    assert st2["leads"] == 1, st2
    client.get("/thanks?checkout_id=polar_c_TEST")
    assert client.get("/stats").json()["checkouts"] == 1, "checkout not counted"
    one = client.get("/onebook?checkout_id=polar_c_ONETIME1234567890abcdef")
    assert one.status_code == 200 and "One book" in one.text and "Reply to the Polar receipt" in one.text, \
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
    for i in range(600):  # over the 150-page free cap, under the 2000-page paid cap
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
    # a long book can take its first 150 pages free, with a closing chapter that sells the rest
    pv = client.post("/convert", files={"f": ("b.pdf", braw, "application/pdf")}, data={"preview": "1"})
    assert pv.status_code == 200, pv.text[:200]
    zv = zipfile.ZipFile(__import__("io").BytesIO(pv.content))
    hv = "".join(zv.read(n).decode("utf-8", "replace") for n in zv.namelist() if n.endswith(".xhtml"))
    assert "page 149" in hv and "page 150" not in hv, "page preview is not the first 150 pages"
    assert "the first 150 of 600 pages" in hv, "page preview does not sell the rest"
    # one upload (11-08): the preview answer says it was cut, so the page pitches $5 without re-sending the file
    assert pv.headers.get("x-cap") == "pages:600", pv.headers
    caps0 = client.get("/stats").json()["cap_rejects"]
    client.post("/convert", files={"f": ("b.pdf", braw, "application/pdf")}, data={"preview": "1"})
    assert client.get("/stats").json()["cap_rejects"] == caps0 + 1, "a preview must still count as a cap hit"
    small = client.post("/convert", files={"f": ("c.pdf", craw, "application/pdf")}, data={"preview": "1"},
                        headers={"x-forwarded-for": "203.0.113.77"})
    assert small.status_code == 200 and "x-cap" not in small.headers, "an under-limit book must not be marked cut"
    from starlette.responses import Response as SR
    jid = pdf2epub._job_start(lambda: SR(b"PK", headers={"X-Cap": "pages:600"}), "", "b.pdf")
    for _ in range(50):
        js = client.get(f"/job/{jid}").json()
        if js["state"] != "queued" and js["state"] != "running":
            break
        time.sleep(0.1)
    assert js.get("cap") == "pages:600", js
    home = client.get("/").text
    assert "fd.append('preview','1')" in home and "window.lastCap" in home and "X-Cap" in home
    assert pdf2epub.MAX_MB >= 500, "a 490MB upload was refused on 11-05; keep the free size cap at 1GB"
    assert "1GB" in home and "200MB" not in home
    assert convert_with("?k=not-a-real-key") == 413, "a junk key must not lift the cap"
    # free whole book for an email (11-12): one book per email, same file reruns free, a second file is refused
    assert client.post("/freebook", data={"email": "nope"}).status_code == 400, "freebook takes a bad email"
    fb = client.post("/freebook", data={"email": "Reader@Example.com", "pages": 600})
    assert fb.status_code == 200 and fb.json()["token"], fb.text
    tok = fb.json()["token"]
    assert client.post("/freebook", data={"email": "reader@example.com"}).status_code == 409, "same email twice"
    whole = client.post("/convert", files={"f": ("b.pdf", braw, "application/pdf")}, data={"preview": "1", "free": tok})
    assert whole.status_code == 200 and not whole.headers.get("X-Cap"), "free book did not convert the whole book"
    again = client.post("/convert", files={"f": ("b.pdf", braw, "application/pdf")}, data={"free": tok})
    assert again.status_code == 200, "rerunning the same free book must stay free"
    other = client.post("/convert", files={"f": ("c.pdf", craw, "application/pdf")}, data={"free": tok})
    assert other.status_code == 402, "a used free token converted a different file"
    assert client.post("/convert", files={"f": ("b.pdf", braw, "application/pdf")},
                       data={"free": "junk"}).status_code == 402, "a junk free token must not lift the cap"
    home2 = client.get("/").text
    assert "freeOffer(n)" in home2 and "/freebook" in home2 and "fd.append('free',window.FREE)" in home2
    junk = client.get("/thanks?checkout_id=nonsense").text
    assert "Shelf key" not in junk, "a junk checkout id must not mint a key"
    fake = client.get("/thanks?checkout_id=polar_c_AAAAAAAAAAAAAAAAAAAAAAAA").text
    assert "Shelf key" not in fake, "a fabricated polar_c id must not mint a key"
    # real polar checkout ids are uuids, and only polar may say a checkout succeeded
    cid = "69c101bb-0ede-4bb1-893f-cf4fd471aab4"
    assert "Shelf key" not in client.get(f"/thanks?checkout_id={cid}").text, \
        "unverified checkout minted a key"
    pdf2epub.paid_checkout = lambda c, p: (c, p) == (cid, pdf2epub.SHELF_PRODUCT)
    real_mail_key, key_mails = pdf2epub._mail_key, []
    pdf2epub._mail_key = lambda c, k, d=0, s=0, cr=0: key_mails.append((c, k, d))
    page = client.get(f"/thanks?checkout_id={cid}").text
    assert "Shelf key" in page, "a verified checkout must mint a key"
    key = re.search(r"\?k=([0-9A-Za-z_-]+)</code>", page).group(1)
    assert convert_with(f"?k={key}") == 200, "a paid key must lift the 150 page cap"
    # 11-05 Jack: a paid 181-page scan was refused as "scan-over-ocr-cap" (paid OCR cap was 120 for an hour).
    # A paid key must OCR a long scan, not refuse it. OCR is stubbed so the test stays fast.
    scan = pymupdf.open()
    for i in range(181):
        scan.new_page().insert_image(pymupdf.Rect(0, 0, 50, 50), stream=pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), 0).tobytes("png"))
    sraw = scan.tobytes()
    scan.close()
    real_ocr = pdf2epub.ocr_doc
    pdf2epub.ocr_doc = lambda doc, layout=False, lang=None, pics=None, confs=None: [("This scanned page reads as ordinary prose with plenty of words. " * 4, 0.5)
                                                  for _ in range(len(doc))]
    sc = client.post(f"/convert?k={key}", files={"f": ("scan.pdf", sraw, "application/pdf")})
    pdf2epub.ocr_doc = real_ocr
    assert sc.status_code == 200, f"paid 181-page scan refused: {sc.status_code} {sc.text[:160]}"
    zs = zipfile.ZipFile(__import__("io").BytesIO(sc.content))
    assert any("ordinary prose" in zs.read(n).decode("utf-8", "replace") for n in zs.namelist() if n.endswith(".xhtml")), \
        "paid long scan skipped OCR (image-only fallback)"
    assert pdf2epub.PAID_OCR_MAX_PAGES >= 600, "paid OCR cap dropped below 600 pages"
    # same checkout must not mint a second key on a page refresh
    again = client.get(f"/thanks?checkout_id={cid}").text
    assert re.search(r"\?k=([0-9A-Za-z_-]+)</code>", again).group(1) == key, "key changed on refresh"
    # 11-07: the key is mailed to the buyer once, on the first mint, never on a refresh
    import time as _t
    for _ in range(50):
        if key_mails:
            break
        _t.sleep(0.02)
    _t.sleep(0.1)
    assert key_mails == [(cid, key, 0)], f"key mail must go out exactly once: {key_mails}"
    assert "emailed it to the address you paid with" in page, "/thanks does not say the key was mailed"
    pdf2epub._mail_key = real_mail_key
    pdf2epub.paid_checkout = real_paid
    # the mail itself: polar order email in, key and link in the body; no email or no resend key, no send
    sent, real_send, real_oe, real_rk = [], pdf2epub._send_mail, pdf2epub._order_email, pdf2epub.RESEND_KEY
    pdf2epub._send_mail = lambda to, subj, body: (sent.append((to, subj, body)), ("opencorp.live", ""))[1]
    pdf2epub.RESEND_KEY = "re_test"
    pdf2epub._order_email = lambda c: "buyer@example.com"
    pdf2epub._mail_key(cid, "KEY123", 30)
    assert len(sent) == 1 and sent[0][0] == "buyer@example.com", sent
    assert "Batch pass" in sent[0][1] and "https://epub.ftak.net/?k=KEY123" in sent[0][2] \
        and "30 days" in sent[0][2], sent[0]
    pdf2epub._order_email = lambda c: ""
    pdf2epub._mail_key(cid, "KEY123")
    pdf2epub.RESEND_KEY = ""
    pdf2epub._order_email = lambda c: "buyer@example.com"
    pdf2epub._mail_key(cid, "KEY123")
    assert len(sent) == 1, "mailed without an email or without a resend key"
    pdf2epub._send_mail, pdf2epub._order_email, pdf2epub.RESEND_KEY = real_send, real_oe, real_rk

    # the $5 one-book converts on the spot: a verified checkout lifts the cap for one file,
    # re-running that same file stays free, a second different book does not ride on it
    bcid = "0b5e3a52-7c1d-4e8f-9a6b-2d4c8e1f3a7b"
    pdf2epub.paid_checkout = lambda c, p: (c, p) == (bcid, pdf2epub.ONEBOOK_PRODUCT)
    assert convert_with(f"?paid={bcid}") == 200, "a paid one-book must lift the 150 page cap"
    assert convert_with(f"?paid={bcid}") == 200, "re-running the paid book must stay free"
    other = client.post(f"/convert?paid={bcid}", files={"f": ("c.pdf", craw, "application/pdf")})
    assert other.status_code == 402, "one payment converted a second, different book"
    assert convert_with("?paid=69c101bb-0ede-4bb1-893f-000000000000") == 402, "unpaid checkout lifted the cap"
    pdf2epub.paid_checkout = real_paid

    # the $3 short book (11-10 price test): lifts the cap for one book up to 400 pages, never past it
    tcid = "3c9a7e21-5b4d-4f6a-8e2c-9d1b0a7f6e54"
    pdf2epub.paid_checkout = lambda c, p: (c, p) == (tcid, pdf2epub.SHORT_PRODUCT)
    mid = pymupdf.open()
    for i in range(300):
        mid.new_page().insert_text((72, 72), f"Page {i + 1} of a mid-length book.", fontsize=11)
    mraw = mid.tobytes()
    assert client.post("/convert", files={"f": ("m.pdf", mraw, "application/pdf")}).status_code == 413, \
        "free tier should stop a 300 page pdf"
    ok3 = client.post(f"/convert?paid={tcid}", files={"f": ("m.pdf", mraw, "application/pdf")})
    assert ok3.status_code == 200, ("a paid $3 book must convert 300 pages", ok3.text[:200])
    # a 600-page book on a fresh $3 checkout: over its 400 pages
    tcid2 = "4d0b8f32-6c5e-4a7b-9f3d-0e2c1b8a7f65"
    pdf2epub.paid_checkout = lambda c, p: (c, p) == (tcid2, pdf2epub.SHORT_PRODUCT)
    over3 = client.post(f"/convert?paid={tcid2}", files={"f": ("b.pdf", braw, "application/pdf")})
    assert over3.status_code == 413 and "400-page limit" in over3.text, over3.text[:200]
    page3 = client.get(f"/onebook?checkout_id={tcid2}").text
    assert "Payment confirmed" in page3 and "up to 400 pages" in page3, "a $3 checkout must confirm with its 400 limit"
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

    # a converter crash must land in conversions.log with its reason and show in /stats (11-07)
    real = pdf2epub._structure
    def boom(*a, **k):
        raise KeyError("no-such-font")
    pdf2epub._structure = boom
    try:
        crash = TestClient(pdf2epub.app, raise_server_exceptions=False).post(
            "/convert?s=crashtest", files={"f": ("x.pdf", make_pdf(), "application/pdf")})
    finally:
        pdf2epub._structure = real
    assert crash.status_code == 500, crash.status_code
    st = client.get("/stats").json()
    assert any(k == "crash KeyError in work" for k in st["fail_by_err"]), st["fail_by_err"]
    last = st["recent_fails"][-1]
    assert last["err"].startswith("crash KeyError") and "no-such-font" in last["err"] and last["src"] == "crashtest", last
    assert "email" not in last, "recent_fails is public: never show emails"
    assert st["starts"] >= 1

    # fake doors (11-07): translate + Mac app buttons, counted in /stats, emails are leads not failures
    for path, word in (("/", "Notify me"), ("/pt/", "Me avise"), ("/es/", "Avísame")):
        page = client.get(path).text
        assert 'id="next" hidden' in page and 'data-want="translate"' in page and 'data-want="desktop"' in page and 'data-want="audio"' in page and 'data-want="kindle"' in page, path
        assert word in page, (path, word)
        assert page.count("static.cloudflareinsights.com/beacon.min.js") == 1, path  # 11-16: CF visitor counter, once
    mac = {"user-agent": "Mozilla/5.0 (Macintosh) Safari/605", "content-type": "application/json"}
    for n in ("want_view", "want_view", "translate_click", "desktop_click", "audio_click", "want_email", "djvu_pick", "kindle_click"):
        client.post("/e", content=json.dumps({"n": n, "v": "wantvisitor1", "why": "desktop"}), headers=mac)
    client.post("/lead", data={"email": "door@e.com", "reason": "want:desktop"}, headers={"user-agent": mac["user-agent"]})
    st = client.get("/stats").json()
    assert st["wants"] == {"want_view": 2, "translate_click": 1, "desktop_click": 1, "audio_click": 1, "want_email": 1,
                           "djvu_pick": 1, "kindle_click": 1, "bilingual_click": 0}, st["wants"]
    # weekly (11-16): Monday-start IST weeks; this week's human visits and conversions show up, bots don't
    wkly = st["weekly"]
    assert wkly and all(set(v) == {"visits_human", "conversions_human", "cap_rejects", "checkouts", "leads"}
                        for v in wkly.values()), wkly
    this = max(wkly)
    assert wkly[this]["visits_human"] >= 1 and sum(v["visits_human"] for v in wkly.values()) <= st["visits_human"], wkly
    # djvu fake door (11-16, Google Trends "djvu to epub" +350%): the picker takes .djvu, the page asks for an email
    # instead of uploading it, and the server still refuses a djvu that gets posted anyway
    for path in ("/", "/pt/", "/es/"):
        page = client.get(path).text
        assert 'accept=".pdf,.djvu,.djv"' in page and "djvuDoor" in page and "want:djvu" in page, path
    r = client.post("/convert", files={"f": ("book.djvu", b"AT&TFORM\x00\x00", "image/vnd.djvu")})
    assert r.status_code == 400, r.status_code
    assert not any(k.startswith("lead") for k in st["fail_by_err"]), st["fail_by_err"]

    # hard wall again (11-22): over the limit there is no free part, the page pitches $5 with the refund in bold.
    # The 11-07 preview: 0 of 136 wall readers paid; the hard wall before it: 2 of 18.
    for path, word in (("/", "<b>Not happy with the book? Full refund, no questions asked.</b>"),
                       ("/pt/", "<b>Não gostou do livro? Reembolso total, sem perguntas.</b>"),
                       ("/es/", "<b>¿No te convence el libro? Te devolvemos todo, sin preguntas.</b>")):
        page = client.get(path).text
        assert "return convert(true)" not in page and 'id="preview"' not in page, path
        assert "if(preview)fd.append('preview','1')" in page and "pitchPages(n)" in page, path
        assert word in page, (path, word)

    # re-download (11-08): a Reddit user got 200 then 404 x2 on the same job; the epub now lives 10 min after the first fetch
    pdf2epub.JOB_DIR.mkdir(parents=True, exist_ok=True)
    jid = "regrab" + "x" * 20
    (pdf2epub.JOB_DIR / f"{jid}.epub").write_bytes(b"PK fake epub")
    pdf2epub._job_write(jid, state="done")
    for _ in range(3):
        r = client.get(f"/job/{jid}/epub")
        assert r.status_code == 200 and r.content == b"PK fake epub", r.status_code
    assert client.get(f"/job/{jid}").json()["state"] == "done", "status poll must not 404 right after the download"
    got = pdf2epub.JOB_DIR / f"{jid}.got"
    assert got.exists()
    old = time.time() - pdf2epub.GOT_GRACE - 5
    os.utime(got, (old, old))
    pdf2epub._job_sweep()
    assert client.get(f"/job/{jid}/epub").status_code == 404, "epub must be gone 10 min after the download"
    assert not got.exists()

    # 11-08: big paid scans run as one long job, never refused; a long-running job survives the 1h sweep
    assert pdf2epub.PAID_OCR_MAX_PAGES >= pdf2epub.SHELF_MAX_PAGES, "paid scans up to the paid page cap must OCR"
    run = "longrun" + "y" * 20
    pdf2epub._job_write(run, state="running")
    old = time.time() - pdf2epub.JOB_TTL - 60
    os.utime(pdf2epub.JOB_DIR / f"{run}.json", (old, old))
    pdf2epub._job_sweep()
    assert client.get(f"/job/{run}").json()["state"] == "running", "sweep killed a running long job"
    # 11-08: every failure tells the reader to mail the PDF in
    for path in ("/", "/pt/", "/es/", "/scan", "/shelf"):
        page = client.get(path).text
        assert "function failHtml" in page and pdf2epub.SHELF_MAIL in page, path
    src = Path(pdf2epub.__file__).read_text()
    for bad in ("by hand", "get it converted", "within a day", "we will convert", "long OCR job"):
        assert bad not in src, f"Polar AUP 11-06: copy must not read as a manual service ({bad!r})"
    assert "msg.textContent=e.message" not in Path(pdf2epub.__file__).read_text(), "a raw error with no mail-us line"

    print("ok: paragraphs joined, header+page number stripped, 2 chapters, email captured, sample.pdf serves, paid key lifts the cap, fulfilment email ok")


if __name__ == "__main__":
    main()


def test_funnel_week():
    # 11-16: week=<Monday> keeps only that IST week, so funnels can be compared week to week
    import json as _j
    from app import funnel_data
    ua = "Mozilla/5.0 (Macintosh) Safari/605"
    mk = lambda t, v, ev: _j.dumps({"t": t, "v": v, "ev": ev, "ua": ua, "src": "x"})
    lines = [mk("2026-11-09T10:00:00+00:00", "a", "view"), mk("2026-11-09T10:01:00+00:00", "a", "pick"),
             mk("2026-11-15T18:29:00+00:00", "b", "view"),   # Sun 23:59 IST: still week of 11-09
             mk("2026-11-15T18:31:00+00:00", "c", "view")]   # Mon 00:01 IST: next week
    w1 = funnel_data(lines, 7, "2026-11-09")["rows"][0]
    w2 = funnel_data(lines, 7, "2026-11-16")["rows"][0]
    assert (w1["view"], w1["pick"], w2["view"]) == (2, 1, 1), (w1, w2)


if __name__ == "__main__":
    test_funnel_week()


def test_nobuy_reason():
    # 11-24: the pitch carries a one-tap "why not buying" row, logged as ev nobuy with a why
    from fastapi.testclient import TestClient
    import app as a
    assert "nobuy" in a.BEACONS
    c = TestClient(a.app)
    html = c.get("/").text
    assert "function nobuy()" in html and "+nobuy()}" in html and "data-nobuy" in html
    r = c.post("/e", content=b'{"n":"nobuy","v":"abcdefgh12","why":"price"}',
               headers={"user-agent": "Mozilla/5.0 (Macintosh) Safari/605"})
    assert r.status_code == 204


if __name__ == "__main__":
    test_nobuy_reason()


def test_bilingual_door():
    # 11-24: r/ebooks launches (Bilingua Reader, GlossPage) show language learners; fake door, clicks + emails decide
    from fastapi.testclient import TestClient
    import app as a
    assert "bilingual_click" in a.BEACONS
    html = TestClient(a.app).get("/").text
    assert 'data-want="bilingual"' in html and "Five things I might build next" in html


if __name__ == "__main__":
    test_bilingual_door()


def test_publish_page():
    # 11-24: author/publisher test page, lead reason author:<store>, ev author_lead
    from fastapi.testclient import TestClient
    import app as a
    c = TestClient(a.app)
    r = c.get("/publish")
    assert r.status_code == 200 and "Author edition: $29 a book" in r.text and "author:" in r.text
    assert "author_lead" in a.BEACONS and "/publish" in a.site_urls()
    assert 'href="/publish"' in c.get("/").text


if __name__ == "__main__":
    test_publish_page()



def test_layer_offer():
    # 11-25 test b: a scan that already has a text layer gets a $1 whole-book offer (rival ~$0.35 a book);
    # the $1 checkout converts only such a scan
    import io
    import pymupdf
    from PIL import Image
    from fastapi.testclient import TestClient
    import app as a
    c = TestClient(a.app)
    r = c.get("/go/layer?why=layer", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == a.LAYER_URL
    html = c.get("/").text
    assert "function pitchLayer(" in html and "/go/layer?why=" in html and "text layer \\(" in html

    img = io.BytesIO()
    Image.new("RGB", (60, 80), (240, 236, 228)).save(img, "JPEG")
    scan = pymupdf.open()
    for i in range(30):
        p = scan.new_page()
        p.insert_image(p.rect, stream=img.getvalue())
        p.insert_text((72, 100), f"Page {i + 1} words of an old scan read long ago.", render_mode=3)
    sraw = scan.tobytes()
    plain = pymupdf.open()
    for i in range(30):
        plain.new_page().insert_text((72, 72), f"Page {i + 1} of a born-digital book.")
    praw = plain.tobytes()

    real = (a.DRIVE_REFRESH, a.layer_scan_pages, a.paid_checkout)
    a._HITS.clear()  # earlier tests in this file used up the per-ip limit
    a.DRIVE_REFRESH = "x"
    a.layer_scan_pages = lambda doc, lang, key="": [(f"Chapter {i + 1}\n\n" + "Real words of the book. " * 20, 1.0)
                                                     for i in range(len(doc))]
    try:
        wall = c.post("/convert", files={"f": ("s.pdf", sraw, "application/pdf")})
        assert wall.status_code == 402 and "text layer (30 here)" in wall.text and "$1" in wall.text, wall.text
        prev = c.post("/convert", data={"preview": "1"}, files={"f": ("s.pdf", sraw, "application/pdf")})
        assert prev.status_code == 200 and prev.headers.get("x-cap") == "layer:30", prev.headers
        lcid = "5e1c9a43-7d6f-4b8a-9c4e-1f3d2b9a8e76"
        a.paid_checkout = lambda cid, p: (cid, p) == (lcid, a.LAYER_PRODUCT)
        wrong = c.post(f"/convert?paid={lcid}", files={"f": ("p.pdf", praw, "application/pdf")})
        assert wrong.status_code == 402 and "already has a text layer" in wrong.text, wrong.text
        ok = c.post(f"/convert?paid={lcid}", files={"f": ("s.pdf", sraw, "application/pdf")})
        assert ok.status_code == 200, ok.text[:200]
    finally:
        a.DRIVE_REFRESH, a.layer_scan_pages, a.paid_checkout = real
    print("ok — layer offer: $1 pitch on OCR-layer scans, checkout converts only those")


if __name__ == "__main__":
    test_layer_offer()


def test_credit_pack():
    # 11-25: $5 = 500 credits on a key, no account; books spend by kind past the free part
    import pymupdf, tempfile
    from pathlib import Path
    from fastapi.testclient import TestClient
    import app as a
    tmp = Path(tempfile.mkdtemp())
    real = (a.SHELF_KEYS, a.CREDITS_USED, a.SHARP_USED, a.paid_checkout, a._mail_key)
    a.SHELF_KEYS, a.CREDITS_USED, a.SHARP_USED = tmp / "k.txt", tmp / "c.txt", tmp / "s.txt"
    a._HITS.clear()
    cid = "6f2d0b54-8e7a-4c9b-ad5f-2e4c3a0b9f87"
    a.paid_checkout = lambda c, p: (c, p) == (cid, a.PACK_PRODUCT)
    a._mail_key = lambda *x: None
    c = TestClient(a.app)
    try:
        r = c.get("/go/pack?why=pages", follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"] == a.PACK_URL
        t = c.get(f"/thanks?checkout_id={cid}").text
        assert "Credit pack" in t and "500 credits" in t, t[:400]
        key = a.SHELF_KEYS.read_text().split()[1]
        assert a.key_credits(key) == 500 and a.credits_left(key) == 500
        assert c.get(f"/credits?k={key}").json() == {"left": 500}
        assert c.get("/credits?k=nosuchkey123").status_code == 404
        # costs: text 341 p = 20 credits past 150, OCR-layer 260 p = 24, OCR 104 p = 84
        assert (a.credit_cost("text", 341), a.credit_cost("layer", 260), a.credit_cost("ocr", 104)) == (20, 24, 84)
        assert a.credit_cost("text", 120) == 0
        d = pymupdf.open()
        for i in range(341):
            d.new_page().insert_text((72, 72), f"Page {i + 1} of a long born-digital book with words.")
        raw = d.tobytes()
        ok = c.post(f"/convert?k={key}", files={"f": ("long.pdf", raw, "application/pdf")})
        assert ok.status_code == 200, ok.text[:200]
        assert a.credits_left(key) == 480, a.credits_left(key)
        assert a.sharp_left(key) == 0, "no AI reading unless the reader ticked it"
        tok = a._AI_PAGES.set(7)
        assert a.sharp_left(key) == 7
        a._AI_PAGES.reset(tok)
        # AI pages spend AI_CREDITS each; the key runs dry, then it is refused before the work
        a.SHARP_USED.write_text(f"{key} 150\n")
        assert a.credits_left(key) == 30
        a.CREDITS_USED.write_text(a.CREDITS_USED.read_text() + f"{key} 25\n")
        short = c.post(f"/convert?k={key}", files={"f": ("long.pdf", raw, "application/pdf")})
        assert short.status_code == 402 and "needs 20 credits" in short.text and "has 5 left" in short.text, short.text
        a.CREDITS_USED.write_text(a.CREDITS_USED.read_text() + f"{key} 5\n")
        assert a.shelf_key(type("R", (), {"query_params": {"k": key}, "headers": {}})()) == "", "empty key still paid"
        html = c.get("/").text
        assert "function packBtn(" in html and "/go/pack?why=" in html and "/credits?k=" in html and "aibox" in html
    finally:
        a.SHELF_KEYS, a.CREDITS_USED, a.SHARP_USED, a.paid_checkout, a._mail_key = real
    print("ok — credit pack: key minted, balance shown, text book spends past 150, refused when short")


if __name__ == "__main__":
    test_credit_pack()
