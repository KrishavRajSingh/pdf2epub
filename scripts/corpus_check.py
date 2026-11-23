"""Convert every book in the corpus folder with this checkout's pipeline and flag what got worse.

usage: python3 scripts/corpus_check.py [corpus_dir=~/free/pdf2epub-corpus] [--jobs 4] [--only name]

The corpus lives outside the repo (readers' books are not ours to commit): <dir>/reader/*.pdf are files
readers sent, <dir>/public/*.pdf are public books, one per kind of PDF (ebook-site novel, LaTeX book,
archive.org scan, ...). Each book is cut to what a reader sees first (150 pages, 20 for a scan), run
through the same path as /convert, and measured:

  splits   paragraphs cut at a page end (open sentence, next one starts lowercase)
  h1       one-letter headings (a drop cap or an icon read as a title)
  rephead  short lines repeated 4+ times (running heads or footers left in the text)
  toc      contents entries        words  words kept        suspect  app._suspect() verdict

Results go to <dir>/results/YYYY-MM-DD.json; the run is compared with the newest earlier file and
exits 1 when a book got worse, so it can gate a deploy or a weekly check.

ponytail (11-22): one missed layout trick (drop caps, a symbol-font page number) breaks every book of
that family, and readers who get a bad file leave without writing. This catches a family before they do.
"""
import collections
import contextlib
import datetime
import io
import json
import os
import re
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

OPEN_END = re.compile(r"[.!?:;\"”’)\]…]\s*$")


def measure(chapters, pages: int) -> dict:
    import app
    paras = [t for ch in chapters for k, t in ch if k == "p" and isinstance(t, str) and t.strip()]
    heads = [t for ch in chapters for k, t in ch if k in ("h1", "h2", "s2", "s3") and isinstance(t, str)]
    latin = sum(c.isascii() for c in "".join(paras[:200])) > 0.6 * max(1, len("".join(paras[:200])))
    splits = sum(1 for a, b in zip(paras, paras[1:]) if latin and b[:1].islower() and not OPEN_END.search(a))
    rep = collections.Counter(p for p in paras if len(p) < 60 and len(p.split()) <= 8 and p[:1] not in "\"“‘'>$#")
    return {"chapters": len(chapters), "toc": len(heads), "h1": sum(1 for h in heads if len(h.strip()) <= 2 and not re.fullmatch(r"[IVXLC]+\.?", h.strip())),
            "splits": splits, "rephead": sum(c for c in rep.values() if c >= 4),
            "words": sum(len(p.split()) for p in paras), "suspect": app._suspect(chapters, pages) or ""}


def run_one(path: str) -> tuple[str, dict]:
    import pymupdf
    import app
    name = Path(path).parent.name + "/" + Path(path).stem
    try:
        doc = pymupdf.open(path)
        with contextlib.redirect_stdout(io.StringIO()):
            if app._ocr_layer(doc) and (app.DRIVE_REFRESH or (Path(path).parent.parent / "cache" / (Path(path).parent.name + "-" + Path(path).stem + ".json")).exists()):
                # ponytail (11-22): live /convert re-reads a scan with an old OCR layer (Drive, then
                # ocr_chapters); the text path is only its fallback. Measure what readers get: the Drive
                # path, its page texts cached per book so a weekly run makes no new Drive calls.
                if len(doc) > 40:
                    doc.select(range(40))
                cache = Path(path).parent.parent / "cache" / (Path(path).parent.name + "-" + Path(path).stem + ".json")
                texts = json.loads(cache.read_text()) if cache.exists() else None
                if texts is not None or app.DRIVE_REFRESH:
                    it = iter(texts or [])
                    pages = app.layer_scan_pages(doc, app.doc_lang(doc), "",
                                                 drive=(lambda img, lang: next(it, None)) if texts is not None else None)
                    if pages and texts is None:
                        cache.parent.mkdir(exist_ok=True)
                        cache.write_text(json.dumps([t for t, _ in pages], ensure_ascii=False))
                    if pages:
                        tx = [t for t, _ in pages]
                        figs = app._scan_figures(doc, pages, {})
                        chapters = app.ocr_chapters(tx, figs, app.pdf_toc(doc))
                        m = measure(chapters, len(doc))
                        m.update(kind="layer", pages=len(doc))
                        return name, m
            blocks = app._text_blocks(doc)
            cut = 150 if blocks else 20
            if len(doc) > cut:
                doc.select(range(cut))
                blocks = app._text_blocks(doc) if blocks else []
            if blocks:
                kind, chapters = "text", app._structure(blocks, doc)
            else:
                tlang, _ = app.ocr_lang(doc)
                pics = {}
                layout = app.ocr_doc(doc, layout=True, lang=tlang, pics=pics) or []
                kind = "ocr"
                chapters = app.ocr_chapters([t for t, _ in layout], app._scan_figures(doc, layout, pics),
                                            app.pdf_toc(doc))
        m = measure(chapters, len(doc))
        m.update(kind=kind, pages=len(doc))
        return name, m
    except Exception as e:  # one broken book must not stop the run
        return name, {"error": f"{type(e).__name__}: {e}"[:200]}


WORSE = {"splits": 2, "h1": 0, "rephead": 3, "toc_jump": 0.5, "words": 0.05}


def compare(old: dict, new: dict) -> list[str]:
    out = []
    for name, m in new.items():
        o = old.get(name)
        if not o or "error" in o:
            continue
        if "error" not in m and (o.get("kind") != m.get("kind") or o.get("pages") != m.get("pages")):
            continue  # measured another way (text 150 p -> Drive 40 p): a new baseline, not a change
        if "error" in m:
            out.append(f"{name}: now fails ({m['error']})")
            continue
        for k in ("splits", "h1", "rephead"):
            if m[k] > o[k] + WORSE[k]:
                out.append(f"{name}: {k} {o[k]} -> {m[k]}")
        if o["words"] and m["words"] < o["words"] * (1 - WORSE["words"]):
            out.append(f"{name}: words {o['words']} -> {m['words']} (text lost?)")
        if o["toc"] and m["toc"] > o["toc"] * (1 + WORSE["toc_jump"]) and m["toc"] - o["toc"] > 5:
            out.append(f"{name}: contents {o['toc']} -> {m['toc']} entries")
        if m["suspect"] and not o["suspect"]:
            out.append(f"{name}: now flagged suspect ({m['suspect']})")
    return out


def main():
    a = sys.argv[1:]
    jobs = int(a[a.index("--jobs") + 1]) if "--jobs" in a else 4
    only = a[a.index("--only") + 1] if "--only" in a else ""
    pos = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or not a[i - 1].startswith("--"))]
    base = Path(os.path.expanduser(pos[0] if pos else "~/free/pdf2epub-corpus"))
    pdfs = sorted(str(p) for p in base.glob("*/*.pdf") if p.exists() and only in p.stem)
    if not pdfs:
        raise SystemExit(f"no PDFs under {base}/*/")
    with ProcessPoolExecutor(jobs) as ex:
        new = dict(ex.map(run_one, pdfs))
    res = base / "results"
    res.mkdir(exist_ok=True)
    today = res / f"{datetime.date.today():%Y-%m-%d}.json"
    earlier = sorted(p for p in res.glob("*.json") if p != today)
    old = json.loads(earlier[-1].read_text()) if earlier else {}
    print(f"{'book':34}{'kind':>5}{'ch':>5}{'toc':>5}{'h1':>4}{'split':>6}{'rep':>5}{'words':>8}  suspect")
    for name, m in new.items():
        if "error" in m:
            print(f"{name:34} ERROR {m['error']}")
            continue
        print(f"{name:34}{m['kind']:>5}{m['chapters']:5}{m['toc']:5}{m['h1']:4}{m['splits']:6}{m['rephead']:5}"
              f"{m['words']:8}  {m['suspect']}")
    # --only adds its rows to today's file (or to the last run's rows when today has none yet)
    mine = json.loads(today.read_text()) if today.exists() else old
    merged = {**mine, **new} if only else new
    today.write_text(json.dumps(merged, indent=1, ensure_ascii=False) + "\n")
    worse = compare(old, new)
    print(f"\nresults: {today}" + (f"  (vs {earlier[-1].name})" if earlier else "  (first run, nothing to compare)"))
    if worse:
        print("WORSE:\n  " + "\n  ".join(worse))
        sys.exit(1)
    print("ok: no book got worse")


if __name__ == "__main__":
    main()
