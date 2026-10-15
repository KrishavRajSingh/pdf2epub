"""PDF -> EPUB MVP. Free text-only. No auth, no DB, no storage."""
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import html
import json
import re
import shutil
import subprocess
import tempfile
import pymupdf
from ebooklib import epub
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
import time

app = FastAPI()
MAX_MB = 50  # ponytail: 100MB like them later, 50 enough to launch
MAX_PAGES = 500  # ponytail: cap keeps free tier fast, raise when paid
LOG = Path("conversions.log")  # ponytail: append-only counts, no file content stored
_HITS: dict[str, list[float]] = {}  # ponytail: in-mem throttle, redis when paid

def log(ok: bool, pages: int, kb_in: int, kb_out: int, err: str = ""):
    try:
        if LOG.exists() and LOG.stat().st_size > 1_000_000:
            LOG.write_text("")  # ponytail: rotate by trunc, log shipper when paid
        with LOG.open("a") as fh:
            fh.write(json.dumps({"t": datetime.now(timezone.utc).isoformat(),
                "ok": ok, "pages": pages, "in": kb_in, "out": kb_out, "err": err[:80]}) + "\n")
    except OSError:
        pass  # ponytail: analytics never breaks conversion

def throttle(request: Request, limit: int = 10, window: int = 60):
    ip = request.client.host if request.client else "?"
    now = time.time()
    hits = [t for t in _HITS.get(ip, []) if now - t < window]
    if len(hits) >= limit:
        raise HTTPException(429, "too many converts, wait a minute")
    hits.append(now)
    _HITS[ip] = hits

def err_page(msg: str, code: int):
    return HTMLResponse(f"<h1>{code}</h1><p>{html.escape(msg)}</p><p><a href='/'>back</a></p>", status_code=code)

def calibre_convert(raw: bytes) -> bytes | None:
    # ponytail: shell to gold-standard engine when ours gives up, None if binary missing/fails
    if not shutil.which("ebook-convert"):
        return None
    try:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.pdf"
            out = Path(td) / "out.epub"
            src.write_bytes(raw)
            subprocess.run(["ebook-convert", str(src), str(out), "--enable-heuristics"],
                timeout=90, check=True, capture_output=True)
            return out.read_bytes() if out.exists() else None
    except Exception:
        return None

PAGE = """<html><head><title>PDF to EPUB — free, real chapters</title>
<meta name="description" content="Free PDF to EPUB with real chapters and TOC for Kindle/Kobo. Text PDFs, no signup.">
<style>body{font-family:system-ui;max-width:640px;margin:40px auto;padding:0 16px}form{border:2px dashed #888;padding:32px;text-align:center}button{padding:12px 24px;font-size:16px}</style>
</head><body><h1>PDF to EPUB — free, real chapters</h1>
<p>Text PDFs only. Scans/OCR, Pro equations, translation skipped for v1. Files deleted after download.</p>
<form action="/convert" method="post" enctype="multipart/form-data">
<input type="file" name="f" accept=".pdf" required><br><br>
<input name="title" placeholder="Title (optional)" maxlength="120"><input name="author" placeholder="Author (optional)" maxlength="120"><br><br>
<button>Convert</button></form></body></html>"""

@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/favicon.ico")
def favicon():
    return HTMLResponse("", status_code=204)

@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    return "<h1>Privacy</h1><p>Files processed in memory, never stored. Counts only (pages, bytes) logged to conversions.log. No accounts in v1.</p><p><a href='/'>back</a></p>"

@app.get("/stats")
def stats():
    # ponytail: totals from log file, no DB/dashboard lib
    ok = fail = pages = 0
    try:
        for line in LOG.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            ok += bool(r.get("ok"))
            fail += not r.get("ok")
            pages += int(r.get("pages", 0))
    except OSError:
        pass
    return {"conversions_ok": ok, "failed": fail, "pages": pages}

def _lines(doc):
    """Yield (page_no, y0, text, size) for each line."""
    for i, page in enumerate(doc):
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                txt = "".join(s["text"] for s in line["spans"]).strip()
                if not txt:
                    continue
                size = max(s["size"] for s in line["spans"])
                y0 = line["bbox"][1]
                yield i, y0, txt, round(size, 1)

@app.post("/convert")
async def convert(request: Request, f: UploadFile = File(...), title: str = Form(""), author: str = Form("")):
    throttle(request)
    raw = await f.read()
    kb_in = len(raw) // 1024
    if len(raw) > MAX_MB * 1024 * 1024:
        log(False, 0, kb_in, 0, "too big")
        raise HTTPException(413, f"over {MAX_MB}MB in v1")
    if not (f.filename or "").lower().endswith(".pdf") or not raw.startswith(b"%PDF"):
        raise HTTPException(400, "PDF only in v1")
    try:
        doc = pymupdf.open(stream=raw, filetype="pdf")
    except Exception:
        log(False, 0, kb_in, 0, "unreadable pdf")
        raise HTTPException(400, "unreadable PDF")
    if len(doc) > MAX_PAGES:
        n0 = len(doc)
        doc.close()
        log(False, n0, kb_in, 0, "too many pages")
        raise HTTPException(413, f"over {MAX_PAGES} pages in v1")

    rows = list(_lines(doc))
    npages = len(doc)
    if not rows:
        # ponytail: try calibre engine before 422, covers scans/complex layout when binary present
        doc.close()
        fb = calibre_convert(raw)
        if fb:
            log(True, npages, kb_in, len(fb) // 1024, "calibre-fallback")
            return StreamingResponse(BytesIO(fb), media_type="application/epub+zip",
                headers={"Content-Disposition": "attachment; filename=book.epub"})
        log(False, npages, kb_in, 0, "scan-no-text")
        raise HTTPException(422, "scanned PDF, no selectable text — OCR not in v1 (install calibre for fallback)")
    long = [s for _, _, t, s in rows if len(t) > 40]
    body = Counter(long).most_common(1)[0][0] if long else Counter(s for _, _, _, s in rows).most_common(1)[0][0]
    h1_cut = body * 1.3
    h2_cut = body * 1.12

    # strip repeated header/footer: same text on >50% pages at top/bottom edge
    tops = Counter(t for p, y, t, _ in rows if y < 60 for p in [p])
    bots = Counter(t for p, y, t, _ in rows if y > doc[0].rect.height - 60 for p in [p])
    n = len(doc)
    banned = {t for t, c in list(tops.items()) + list(bots.items()) if c > n * 0.5}

    chapters, cur = [], []
    def flush():
        if cur:
            chapters.append(cur.copy())
            cur.clear()
    for _, _, t, s in rows:
        if t in banned or re.fullmatch(r"\d+", t):
            continue  # ponytail: page numbers/running heads dropped, no config
        if s >= h1_cut and len(t) < 120:
            flush()
            cur.append(("h1", t))
        elif s >= h2_cut and len(t) < 120:
            cur.append(("h2", t))
        else:
            cur.append(("p", t))
    flush()

    book = epub.EpubBook()
    safe_title = (title or (f.filename or "book").rsplit(".", 1)[0])[:120] or "book"
    book.set_title(safe_title)
    if author[:120]:
        book.add_author(author[:120])
    book.set_language("en")
    items, toc = [], []
    for i, ch in enumerate(chapters or [[("p", "empty")]]):
        c = epub.EpubHtml(title=f"ch{i+1}", file_name=f"ch{i+1}.xhtml")
        c.content = "".join(
            f"<h1>{html.escape(t)}</h1>" if k == "h1" else f"<h2>{html.escape(t)}</h2>" if k == "h2" else f"<p>{html.escape(t)}</p>"
            for k, t in ch
        )
        book.add_item(c)
        items.append(c)
        toc.append(c)
    book.toc = tuple(toc)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + items
    buf = BytesIO()
    epub.write_epub(buf, book)
    buf.seek(0)
    # ponytail: nothing stored, files die with request — matches their privacy pitch for free
    log(True, npages, kb_in, len(buf.getvalue()) // 1024)
    doc.close()
    return StreamingResponse(buf, media_type="application/epub+zip",
        headers={"Content-Disposition": "attachment; filename=book.epub"})

@app.exception_handler(HTTPException)
async def http_err(request: Request, exc: HTTPException):
    if "text/html" in request.headers.get("accept", ""):
        return err_page(str(exc.detail), exc.status_code)
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, port=8000)
