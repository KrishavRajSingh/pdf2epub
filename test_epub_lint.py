"""scripts/epub_lint.py: a clean EPUB passes, and each defect from the Paramattha book (11-21) is caught.

The PDF and EPUBs are made here, so no reader's book sits in the repo.
"""
import io
import zipfile

import pymupdf
import pytest
from PIL import Image

from scripts.epub_lint import lint

LIST = ["Sadness", "Weakness", "Confusion", "Agitation"]
BODY = ("This is a long body line of running text that fills the measure of the page from margin to "
        "margin so it reads as prose.")


def _png(color):
    b = io.BytesIO()
    Image.radial_gradient("L").convert("RGB").save(b, "PNG") if color == "pic" else \
        Image.new("RGB", (64, 64), (128, 128, 128)).save(b, "PNG")
    return b.getvalue()


@pytest.fixture(scope="module")
def pdf(tmp_path_factory):
    path = tmp_path_factory.mktemp("lint") / "book.pdf"
    doc = pymupdf.open()
    p = doc.new_page(width=432, height=648)
    p.insert_text((57, 60), "CHAPTER ONE", fontsize=15)
    p.insert_textbox(pymupdf.Rect(57, 80, 380, 160), BODY, fontsize=12)
    for i, t in enumerate(LIST):
        p.insert_text((57, 200 + 14 * i), t, fontsize=11)
    p.insert_image(pymupdf.Rect(100, 300, 300, 450), stream=_png("pic"))
    p2 = doc.new_page(width=432, height=648)
    p2.insert_text((57, 60), "THE SUB PART", fontsize=13)
    p2.insert_textbox(pymupdf.Rect(57, 80, 380, 160), BODY, fontsize=12)
    doc.set_toc([[1, "Chapter One", 1], [2, "The Sub Part", 2]])
    doc.save(path)
    return str(path)


GOOD = {
    "ch1": f"<h1>CHAPTER ONE</h1><p>{BODY}</p><p>{'<br/>'.join(LIST)}</p>"
           '<figure><img src="images/a.png" alt=""/></figure>',
    "ch2": f"<h2>THE SUB PART</h2><p>{BODY}</p>",
}


def _epub(path, chapters, nav=("Chapter One", "The Sub Part"), pic="pic", extra=None):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        for name, body in chapters.items():
            z.writestr(f"OEBPS/{name}.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
                                               f"{body}</body></html>")
        z.writestr("OEBPS/nav.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml" '
                   'xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol>'
                   + "".join(f"<li><a>{t}</a></li>" for t in nav) + "</ol></nav></body></html>")
        z.writestr("OEBPS/images/a.png", _png(pic))
        for k, v in (extra or {}).items():
            z.writestr(k, v)
    return str(path)


def kinds(pdf, epub):
    return {f.split()[0] for f in lint(pdf, epub)}


def test_clean_book_passes(pdf, tmp_path):
    assert lint(pdf, _epub(tmp_path / "ok.epub", GOOD)) == []


@pytest.mark.parametrize("kind,change", [
    ("FONT", dict(extra={"OEBPS/fonts/x.ttf": b"0"})),
    ("TOC", dict(nav=("Chapter One",))),
    ("BLANK", dict(pic="flat")),
    ("SPACED", dict(chapters={**GOOD, "ch1": GOOD["ch1"].replace("CHAPTER ONE", "C H A P T E R O N E")})),
    ("HEAD-", dict(chapters={**GOOD, "ch2": "<h2>THE SUB-</h2><p>PART</p>" + f"<p>{BODY}</p>"})),
    ("HEAD?", dict(chapters={**GOOD, "ch2": f"<p>THE SUB PART</p><p>{BODY}</p>"})),
    ("COLUMNS", dict(chapters={**GOOD, "ch2": GOOD["ch2"] + "<p>(1) seeing (14) balance (2) hearing</p>"})),
    ("LINES", dict(chapters={**GOOD, "ch1": GOOD["ch1"].replace("<br/>", " ")})),
    ("HYPHEN", dict(chapters={**GOOD, "ch2": GOOD["ch2"] + "<p>it distin- guishes a rat from a cat</p>"})),
])
def test_each_defect_is_flagged(pdf, tmp_path, kind, change):
    args = {"chapters": GOOD, **change}
    assert kind in kinds(pdf, _epub(tmp_path / f"{kind}.epub", **args))
