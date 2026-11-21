"""Check a finished EPUB against its PDF, with rules only (no AI, no eyes needed).

usage: python3 scripts/epub_lint.py book.pdf book.epub

Every flag below is a defect a reader or a store would see. Each rule exists because a real book
had that defect and only a human page-by-page look found it (Paramattha, 11-21):

  FONT     embedded font files or @font-face (Draft2Digital and other stores refuse them)
  SIZE     EPUB over 100 MB (Draft2Digital's cap)
  TOC      PDF bookmarks (any level) with no matching entry in the EPUB contents
  PICS     the PDF shows more pictures than the EPUB holds
  BLANK    a picture that is one flat colour (an overlay or mask exported alone)
  SPACED   letter-spaced text that came out as "B O D Y , M I N D"
  HEAD-    a heading that ends in a hyphen or is followed by an all-caps scrap (one heading split in two)
  HEAD?    a bookmark title printed in the PDF that the EPUB shows as a normal paragraph
  COLUMNS  numbered items out of order inside one paragraph: "(10) ... (21)" = two columns merged
  LINES    a run of short PDF lines (a list or a poem) that the EPUB glued into running prose
  HYPHEN   "distin- guishes": a line-end hyphen left inside a word
  MARK     a paragraph that is only a note marker ("§", "†", "***") torn off its sentence
  SPLIT    a paragraph that stops mid-sentence and the next one goes on in lowercase
  WORDS    share of PDF words (4+ letters) found in the EPUB
Exit 1 when anything is flagged.
"""
import html
import io
import re
import sys
import unicodedata
import zipfile
from collections import Counter

import pymupdf
from lxml import etree

MAX_MB = 100
W = re.compile(r"[^\W\d_]+")


def norm(s: str) -> str:
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFC", s).lower())


def words(s: str) -> list[str]:
    return W.findall(unicodedata.normalize("NFC", s).lower())


def epub_parts(path):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    docs, heads, paras, stream = [], [], [], []
    for n in names:
        if not n.endswith((".xhtml", ".html", ".htm")):
            continue
        raw = z.read(n)
        if b'epub:type="toc"' in raw or n.endswith("nav.xhtml"):
            continue
        t = etree.fromstring(raw.replace(b"<br/>", b"<br/>\n"))
        for el in t.iter():
            tag = etree.QName(el).localname if isinstance(el.tag, str) else ""
            if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                heads.append((n, " ".join("".join(el.itertext()).split())))
            elif tag in ("p", "td", "li", "figcaption"):
                paras.append((n, "".join(el.itertext())))
        # text stream with "\n" at every paragraph or line break, for the LINES rule
        s = re.sub(r"<br\s*/?>|</(p|h\d|li|td|div|figcaption)>", "\n", raw.decode("utf-8", "replace"))
        stream.append(html.unescape(re.sub(r"<[^>]+>", "", s)))
    nav = ""
    for n in names:
        raw = z.read(n)
        if n.endswith((".xhtml", ".html")) and b'epub:type="toc"' in raw or n.endswith(".ncx"):
            nav += html.unescape(re.sub(r"<[^>]+>", " ", raw.decode("utf-8", "replace")))
    return z, names, heads, paras, "\n".join(stream), nav


def lint(pdf_path: str, epub_path: str) -> list[str]:
    doc = pymupdf.open(pdf_path)
    z, names, heads, paras, stream, nav = epub_parts(epub_path)
    flags = []

    # FONT / SIZE
    fonts = [n for n in names if n.lower().endswith((".ttf", ".otf", ".woff", ".woff2"))]
    css_ff = [n for n in names if n.endswith((".css", ".xhtml")) and b"@font-face" in z.read(n)]
    if fonts or css_ff:
        flags.append(f"FONT     {len(fonts)} font files, @font-face in {len(css_ff)} files")
    mb = sum(i.file_size for i in z.infolist()) / 1e6
    if mb > MAX_MB:
        flags.append(f"SIZE     {mb:.0f} MB > {MAX_MB} MB")

    # TOC: every bookmark should be findable in the contents (split bookmarks may share one entry)
    navn = norm(nav)
    toc = doc.get_toc()
    miss = [t for _, t, _, *_ in toc if t.strip() and norm(t) not in navn]
    if miss:
        flags.append(f"TOC      {len(miss)}/{len(toc)} bookmarks not in the contents: {miss[:5]}")

    # PICS / BLANK
    shown = set()
    for p in doc:
        for im in p.get_images(full=True):
            if any(r.width >= 12 and r.height >= 12 for r in p.get_image_rects(im[0])):
                shown.add(im[0])
    imgs = [n for n in names if n.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))]
    if len(imgs) + 1 < len(shown) * 0.9:
        flags.append(f"PICS     PDF shows {len(shown)} pictures, EPUB has {len(imgs)}")
    from PIL import Image, ImageStat
    for n in imgs:
        try:
            im = Image.open(io.BytesIO(z.read(n))).convert("L")
        except Exception:
            continue
        im.thumbnail((200, 200))
        if ImageStat.Stat(im).stddev[0] < 4:
            flags.append(f"BLANK    {n} is one flat colour")

    # SPACED
    for n, t in heads + paras:
        m = re.search(r"(?:\b\w ){5,}\w\b", t)
        if m and len(re.findall(r"\b\w\b", t)) > 0.4 * len(t.split()):
            flags.append(f"SPACED   {n}: {m.group(0)[:50]!r}")

    # HEAD- / HEAD?
    for i, (n, t) in enumerate(heads):
        if re.search(r"\w-$", t):
            flags.append(f"HEAD-    {n}: {t[:60]!r}")
    for i, (n, t) in enumerate(paras):
        if i and re.fullmatch(r"[A-Z0-9 ,'’&:/-]{3,60}", t.strip()) and paras[i - 1][1].strip().endswith("-"):
            flags.append(f"HEAD-    {n}: caps scrap after hyphen {t.strip()[:40]!r}")
    headn = {norm(t) for _, t in heads}
    for _, t, _, *_ in toc:
        tn = norm(t)
        if len(tn) > 6 and not any(tn in h or (h and h in tn and len(h) > 0.5 * len(tn)) for h in headn):
            if any(norm(p) == tn for _, p in paras):
                flags.append(f"HEAD?    bookmark {t!r} is a plain paragraph")

    # COLUMNS
    for n, t in paras:
        nums = [int(x) for x in re.findall(r"\((\d{1,3})\)", t)]
        if len(nums) >= 2 and any(b - a > 3 or b <= a for a, b in zip(nums, nums[1:])):
            flags.append(f"COLUMNS  {n}: numbered items out of order {nums[:8]} in {t[:50]!r}")

    # LINES: 3+ consecutive short PDF lines (list / poem) must keep their breaks in the EPUB
    flat = re.sub(r"[ \t]+", " ", unicodedata.normalize("NFC", stream))
    for pi, page in enumerate(doc):
        wpage = page.rect.width
        lines = []
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                t = "".join(s["text"] for s in l["spans"]).strip()
                if t:
                    lines.append((l["bbox"], t))
        run = []
        for bbox, t in lines + [((0, 0, wpage, 0), "")]:
            short = t and bbox[2] < wpage * 0.62 and len(t) > 3 and not t.endswith("-")
            if short:
                run.append(t)
                continue
            if len(run) >= 3:
                glued = 0
                for a, b in zip(run, run[1:]):
                    a2, b2 = unicodedata.normalize("NFC", a), unicodedata.normalize("NFC", b)
                    if re.search(re.escape(a2[-15:]) + r" " + re.escape(b2[:10]), flat):
                        glued += 1
                if glued >= max(2, len(run) // 2):
                    flags.append(f"LINES    p{pi + 1}: {len(run)} short lines glued into prose, from {run[0][:40]!r}")
            run = []

    # MARK / SPLIT
    marks = [n for n, t in paras if t.strip() and re.fullmatch(r"[\s*†‡§¶#⁰¹²³⁴⁵⁶⁷⁸⁹\d]{1,8}", t.strip())
             and not t.strip().isdigit()]
    if marks:
        flags.append(f"MARK     {len(marks)} paragraphs that are only a note marker (first in {marks[0]})")
    splits = [(n, a, b) for (n, a), (n2, b) in zip(paras, paras[1:]) if n == n2 and a.strip() and b.strip()
              and b.strip()[:1].islower() and not re.search(r"[.:;!?\"”’)\]]\W*$", a.strip())]
    if len(splits) > 2:
        n, a, b = splits[0]
        flags.append(f"SPLIT    {len(splits)} paragraphs cut mid-sentence, first {a.strip()[-30:]!r} | {b.strip()[:20]!r}")

    # HYPHEN
    book = Counter(words(" ".join(t for _, t in paras)))
    # "sense- impressions" typed that way mid-line is the author's spelling, not a leftover line break
    pdf_inline = {(a.lower(), b.lower()) for p in doc
                  for a, b in re.findall(r"([^\W\d_]{2,})- ([^\W\d_]{2,})", unicodedata.normalize("NFC", p.get_text()))}
    for n, t in paras:
        for a, b in re.findall(r"\b([^\W\d_]{2,})- ([a-zà-ỹ]{2,})\b", unicodedata.normalize("NFC", t)):
            if (a.lower(), b.lower()) in pdf_inline:
                continue
            if book[(a + b).lower()] or not book[f"{a}-{b}".lower()]:
                flags.append(f"HYPHEN   {n}: {a}- {b}")

    # WORDS
    pw = Counter(w for p in doc for w in words(re.sub(r"-\n", "", p.get_text())) if len(w) >= 4)
    ew = Counter(w for w in words(stream.replace("-", "")) if len(w) >= 4)
    ew.update(w for w in words(stream) if len(w) >= 4)
    tot = sum(pw.values())
    lost = sum(max(0, c - ew[w]) for w, c in pw.items())
    share = 100 * (1 - lost / max(1, tot))
    if share < 97:
        flags.append(f"WORDS    only {share:.1f}% of PDF words found (pictures of tables count as missing)")
    return flags


if __name__ == "__main__":
    out = lint(sys.argv[1], sys.argv[2])
    kinds = Counter(f.split()[0] for f in out)
    for f in out[:200]:
        print(f)
    print("summary:", dict(kinds) or "clean")
    sys.exit(1 if out else 0)
