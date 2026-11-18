"""Audit one PDF's conversion without looking at it: flag output that mixes what the PDF keeps apart.

usage: python3 scripts/audit.py book.pdf

Each output block is traced back to the PDF blocks it was built from. Flags:
  MIXED   a body paragraph holds text from a page-foot small-type block (a footnote glued into
          the prose, the 11-18 "two sections wrongly merged" report) or the reverse
  NOTE?   a page-foot small-type block that starts with a note marker but is not in Notes
  HEAD?   a heading set in body size with no heading word (a quote line or column-top fragment)
  GONE    a printed line whose words never reach the book in order (a dropped entry, 11-18)
  LOST    PDF words (4+ letters) that never reach the EPUB, beyond running heads and hyphen parts
Exit 1 when anything is flagged, so a lead's file can be checked before the reply goes out.
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pymupdf
import app


def audit(path: str) -> list[str]:
    doc = pymupdf.open(path)
    blocks = list(app._blocks(doc))
    chapters = app._structure(blocks, doc)
    text = [b for b in blocks if b[2] > 0 and isinstance(b[3], str)]
    sizes = Counter()
    for _, _, sz, t in text:
        sizes[sz] += len(t)
    body = sizes.most_common(1)[0][0]

    def foot(b):
        p, y, sz, _ = b
        return sz < body * 0.95 and y > doc[p].rect.height * 0.55

    flags = []
    items = [it for ch in chapters for it in ch if isinstance(it[1], str)]
    for kind, out in items:
        if kind not in ("p", "fn"):
            continue
        # source blocks long enough to be identified inside this output block
        src = [b for b in text if len(b[3]) >= 30 and b[3] in out]
        has_foot = any(foot(b) for b in src)
        has_body = any(b[2] >= body * 0.95 for b in src)
        if kind == "p" and has_foot and has_body:
            flags.append(f"MIXED body paragraph holds footnote text: …{out[:90]}…")
        if kind == "fn" and has_body:
            flags.append(f"MIXED note holds body text: …{out[:90]}…")
    notes = " ".join(t for k, t in items if k == "fn")
    fn_mark = re.compile(r"^\d{1,3}\s+[A-Z“\"]")
    for b in text:
        if foot(b) and fn_mark.match(b[3]) and len(b[3]) > 30 and b[3][:60] not in notes:
            flags.append(f"NOTE? foot note not in Notes: {b[3][:90]}")
    heads = [t for k, t in items if k in ("h1", "h2")]
    for b in text:
        if b[3] in heads and abs(b[2] - body) < 0.3 and not re.match(
                r"(chapter|part|\d+(\.\d+)*\s|references|bibliography|notes|appendix|abstract)", b[3], re.I):
            flags.append(f"HEAD? body-size heading: {b[3][:90]}")
    # every printed line must reach the book, in its words and their order. Drop the first and
    # last word (hyphen splits at line ends), skip lines repeated on 3+ pages (running heads).
    # letters only: note markers print as "1" in the PDF and "¹" in the book
    seq = lambda s: " ".join(w.lower() for w in re.findall(r"[^\W\d_]+", re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹\u200b]", "", s)))
    book = seq(" ".join(t for _, t in items))
    seen = Counter()
    lines = []
    cover = max((k for k in range(min(3, len(doc))) if app.OFFPRINT.search(doc[k].get_text("text"))), default=-1)
    for pg in doc:
        if pg.number <= cover:
            continue  # publisher offprint cover + notice pages are dropped on purpose
        for b in pg.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                t = "".join(s["text"] for s in ln["spans"]).strip()
                if len(t) >= 25 and not re.match(r"https?://doi\.org/|Publisher’s Note|jurisdictional claims", t):
                    lines.append(t)
                    seen[t] += 1
    gone = [t for t in lines if seen[t] < 3 and len(seq(t).split()) >= 5
            and " ".join(seq(t).split()[1:-1]) not in book]
    for t in gone[:15]:
        flags.append(f"GONE printed line not in the book: {t[:90]}")
    W = lambda s: Counter(w.lower() for w in re.findall(r"[A-Za-z]{4,}", s))
    src_w, out_w = W(" ".join(b[3] for b in text)), W(" ".join(t for _, t in items))
    lost = sum(max(0, src_w[w] - out_w[w]) for w in src_w)
    banned = sum(src_w[w] for w in src_w if out_w[w] == 0)  # repeated heads/watermarks never reach the book
    if lost - banned > max(20, sum(src_w.values()) * 0.01):
        top = sorted(((src_w[w] - out_w[w], w) for w in src_w if 0 < out_w[w] < src_w[w]), reverse=True)[:10]
        flags.append(f"LOST {lost - banned} words partly missing: {top}")
    return flags


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    found = audit(sys.argv[1])
    print("\n".join(found) or "clean: no mixed blocks, notes in place, no body-size headings, no lost text")
    sys.exit(1 if found else 0)
