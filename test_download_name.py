"""Downloads are named after the uploaded PDF, not "book.epub" (ysvsr 11-14: a folder of Telugu
books all came out as the same name, because the header beats the page's a.download).

Run: python3 test_download_name.py
"""
import os, sys, tempfile, time
from pathlib import Path
from urllib.parse import unquote

os.environ["LOG_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pymupdf
from fastapi.testclient import TestClient
import app as pdf2epub


def pdf():
    doc = pymupdf.open()
    for i in range(3):
        doc.new_page().insert_text((72, 72), f"Chapter {i + 1}\n\n" + "Plain words in a line. " * 40)
    return doc.tobytes()


def name_of(r):
    cd = r.headers["content-disposition"]
    assert "filename*=UTF-8''" in cd, cd
    return unquote(cd.split("filename*=UTF-8''", 1)[1])


def main():
    d = pdf2epub._epub_disp
    assert name_of(type("R", (), {"headers": {"content-disposition": d("Gorky_Mother.PDF")}})) == "Gorky_Mother.epub"
    assert 'filename="book.epub"' in d("")
    assert '"' not in d('a"b.pdf').split("filename=", 1)[1].split(";")[0].strip('"')

    c = TestClient(pdf2epub.app)
    te = "మైదానం - చలం.pdf"
    r = c.post("/convert", files={"f": (te, pdf(), "application/pdf")})
    assert r.status_code == 200, r.text[:200]
    assert name_of(r) == "మైదానం - చలం.epub", r.headers["content-disposition"]

    # job path (big books, folders): the name survives into /job/<id>/epub
    r = c.post("/convert", files={"f": ("Second Book.pdf", pdf(), "application/pdf")}, headers={"X-Job": "1"})
    assert r.status_code == 202, r.status_code
    j = r.json()["job"]
    for _ in range(120):
        if c.get(f"/job/{j}").json().get("state") == "done":
            break
        time.sleep(0.5)
    r = c.get(f"/job/{j}/epub")
    assert r.status_code == 200 and name_of(r) == "Second Book.epub", r.headers.get("content-disposition")

    # key box on the home page, for a key bought on another device
    assert 'id="keyform"' in c.get("/").text
    print("ok: EPUBs keep the PDF's name, key box on home")


if __name__ == "__main__":
    main()
