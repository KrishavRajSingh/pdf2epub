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

    # email capture + sample endpoint
    st = client.get("/stats").json()
    assert st["emails_captured"] == 1, st
    s = client.get("/sample.pdf")
    assert s.status_code == 200 and s.content[:4] == b"%PDF", "sample.pdf broken"

    print("ok: paragraphs joined, header+page number stripped, 2 chapters, email captured, sample.pdf serves")


if __name__ == "__main__":
    main()
