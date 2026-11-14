"""Translate PDF: free pages, scans as images, output PDF, paid unlock refused without payment, CORS.

Run: python3 test_translate.py   (no model calls: the model is replaced by a fake)
"""
import os, tempfile, time

os.environ["LOG_DIR"] = tempfile.mkdtemp()
os.environ["JOB_DIR"] = tempfile.mkdtemp()
os.environ.setdefault("OPENROUTER_API_KEY", "test")
import pymupdf
from fastapi.testclient import TestClient
import app as pdf2epub
import translate

SEEN = []


def fake_ask(content, lang):
    if isinstance(content, list):  # scan page went as an image
        SEEN.append("image")
        return "# Titulo escaneado\n\nTexto de una pagina escaneada."
    SEEN.append("text")
    return "# Capitulo\n\nEste es un parrafo traducido.\n\nOtro parrafo."


def make_pdf(pages: int, scan_at: int = -1) -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        if i == scan_at:
            page.draw_rect(pymupdf.Rect(72, 72, 300, 200), color=(0, 0, 0), fill=(0.5, 0.5, 0.5))
            continue
        page.insert_text((72, 100), f"Chapter {i + 1}", fontsize=20)
        page.insert_textbox(pymupdf.Rect(72, 130, 520, 400), "This is a sentence of the source text. " * 6,
                            fontsize=11)
    raw = doc.tobytes()
    doc.close()
    return raw


def wait(c, jid):
    for _ in range(200):
        st = c.get(f"/translate/{jid}").json()
        if st["status"] != "working":
            return st
        time.sleep(0.05)
    raise AssertionError("job never finished")


def main():
    translate._ask = fake_ask
    c = TestClient(pdf2epub.app)

    # CORS preflight from ftak.net is allowed, others get no allow-origin
    r = c.options("/translate", headers={"Origin": "https://ftak.net", "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "https://ftak.net", r.headers
    r = c.options("/translate", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers

    # 25 pages, page 3 is a scan: only the first 20 are translated free, the scan goes as an image
    r = c.post("/translate", files={"f": ("my book.pdf", make_pdf(25, scan_at=2), "application/pdf")},
               data={"lang": "es"}, headers={"Origin": "https://ftak.net"})
    assert r.status_code == 200, r.text
    assert r.headers.get("access-control-allow-origin") == "https://ftak.net"
    jid = r.json()["job"]
    st = wait(c, jid)
    assert st["status"] == "done" and st["translated"] == 20 and st["pages"] == 25, st
    assert st["more_pages"] == 5, st
    assert SEEN.count("image") == 1 and SEEN.count("text") == 19, SEEN
    r = c.get(f"/translate/{jid}/pdf")
    assert r.status_code == 200 and "Spanish" in r.headers["content-disposition"], r.headers
    out = pymupdf.open(stream=r.content, filetype="pdf")
    text = " ".join(" ".join(p.get_text() for p in out).split())
    assert out.page_count == 21, out.page_count  # 20 translated pages + the "translate the rest" note
    assert "Capitulo" in text and "Titulo escaneado" in text and "Page 20" in text, text[:300]
    assert "20 of 25 pages" in text

    # unpaid unlock is refused, bad input is refused
    r = c.post(f"/translate/{jid}/full", data={"checkout": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 402, r.text
    r = c.post("/translate", files={"f": ("x.pdf", b"not a pdf", "application/pdf")}, data={"lang": "es"})
    assert r.status_code == 400
    r = c.post("/translate", files={"f": ("x.pdf", make_pdf(1), "application/pdf")}, data={"lang": "xx"})
    assert r.status_code == 400
    assert c.get("/translate/not-a-real-job-id-at-all").status_code == 404

    # a short PDF is translated whole, with no "rest" note
    SEEN.clear()
    r = c.post("/translate", files={"f": ("short.pdf", make_pdf(2), "application/pdf")}, data={"lang": "hi"})
    st = wait(c, r.json()["job"])
    assert st["translated"] == 2 and st["more_pages"] == 0 and st["checkout"] == "", st
    assert c.get("/go/translate", follow_redirects=False).status_code == 302
    out = pymupdf.open(stream=c.get(f"/translate/{r.json()['job']}/pdf").content, filetype="pdf")
    assert out.page_count == 2

    # right-to-left and non-Latin output renders without error
    pdf = translate.build_pdf([(1, "# عنوان\n\nهذا نص مترجم."), (2, "यह अनुवाद है।"), (3, None)], "ar")
    out = pymupdf.open(stream=pdf, filetype="pdf")
    assert out.page_count == 3 and "could not be translated" in out[2].get_text()
    print("ok translate")


if __name__ == "__main__":
    main()
