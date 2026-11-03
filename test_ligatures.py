"""Self-check: a PDF whose font maps its ligature glyphs to the wrong Unicode (first buyer's
book: "fi" read as "Dž", "ff" as "!") comes out with the real letters, real "!" kept, and a
sentence cut by a page break stays one paragraph.
Run: python3 test_ligatures.py"""
import re
import pymupdf
from app import _blocks, _structure

FONT = "/System/Library/Fonts/Supplemental/Georgia.ttf"  # has all five ligature glyphs
PAGE1 = ["Carter waved his hand. “You’re someone that people want to",
         "do a good job for. It’s motivational stuﬀ. I",
         "would love to be on that team"]
PAGE2 = ["—no,” he paused, correcting himself with a ﬁnger in the",
         "air. The oﬃce was ﬂat and the coach was diﬀerent today.",
         "“Wow!” she said. “Stop!” He oﬀered a ﬁrst coffee."]
PAGE3 = ["They ﬁnally found the ﬁeld. It was diﬃcult and the",
         "ﬂag was ﬂuttering over the oﬃcers by the ﬁre. Her eﬀort",
         "made a diﬀerence, and she suﬀered no more."]


def make_pdf() -> bytes:
    doc = pymupdf.open()
    for lines in (PAGE1, PAGE2, PAGE3):
        p = doc.new_page(width=420, height=300)
        p.insert_font(fontname="G", fontfile=FONT)
        p.insert_text((20, 120), "\n".join(lines), fontname="G", fontsize=11, lineheight=1.4)
    # break the ToUnicode map the way her book's font is broken
    x = next(int(m) for k in range(1, doc.xref_length())
             for m in re.findall(r"/ToUnicode (\d+) 0 R", doc.xref_object(k)))
    cmap = doc.xref_stream(x).decode()
    for good, bad in {"fb01": "01c5", "fb00": "0021", "fb03": "0022"}.items():
        cmap = re.sub(f"<{good}>", f"<{bad}>", cmap, flags=re.I)
    doc.update_stream(x, cmap.encode())
    return doc.tobytes()


doc = pymupdf.open(stream=make_pdf(), filetype="pdf")
raw = "".join(pg.get_text() for pg in doc)
assert "stu!." in raw and "ǅnger" in raw, "test PDF should reproduce the broken map"
paras = [t for ch in _structure(list(_blocks(doc)), doc) for k, t in ch if k == "p"]
text = "\n".join(paras)
print(text)
for w in ("stuff.", "finger", "office", "flat", "different", "offered", "first",
          "finally", "field", "difficult", "flag", "fluttering", "officers", "fire", "effort", "difference", "suffered"):
    assert w in text, w
assert "“Wow!”" in text and "“Stop!”" in text, "real ! must stay"
assert "ǅ" not in text and "stu!" not in text
assert any("on that team—no," in p or "on that team —no," in p for p in paras), \
    "sentence cut by a page break must stay one paragraph"
print("ok")

# a chapter heading the PDF writes after the chapter's first paragraphs (AO3/Kindle export)
doc = pymupdf.open()
for n in (1, 2):
    p = doc.new_page(width=420, height=500)
    p.insert_text((20, 200), f"Body of chapter {n} starts here and runs on for a while, as prose does.\n"
                  "It keeps going with a second sentence so the block looks like body text.", fontsize=11)
    p.insert_text((20, 60), f"Chapter {n}: a title", fontsize=20)
paras = [(k, t) for ch in _structure(list(_blocks(doc)), doc) for k, t in ch]
assert paras[0] == ("h1", "Chapter 1: a title") and paras[1][1].startswith("Body of chapter 1"), paras[:3]
print("heading order ok")
