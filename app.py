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

PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PDF to EPUB — free, real chapters for Kindle</title>
<meta name="description" content="Free PDF to EPUB with real chapters and TOC for Kindle/Kobo/Apple Books. Text PDFs, no signup, files deleted after download.">
<style>
:root{--bg:#0f1115;--card:#171b22;--line:#2a3140;--txt:#e8ecf3;--mut:#9aa4b5;--acc:#7c5cff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:720px;margin:0 auto;padding:40px 20px 64px}
.hero{text-align:center;margin-bottom:28px}.hero h1{font-size:40px;margin:0 0 8px;letter-spacing:-1px}
.hero h1 span{color:var(--acc)}.hero p{color:var(--mut);margin:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:28px;margin-top:24px}
#drop{border:2px dashed var(--line);border-radius:12px;padding:36px 20px;text-align:center;cursor:pointer;transition:.15s}
#drop.over{border-color:var(--acc);background:#1d2230}
#drop b{font-size:18px}#fname{color:var(--mut);margin-top:8px;font-size:14px}
.row{display:flex;gap:10px;margin-top:14px}.row input{flex:1;background:#0f1319;border:1px solid var(--line);color:var(--txt);border-radius:10px;padding:12px}
button{background:var(--acc);color:#fff;border:0;border-radius:10px;padding:14px 22px;font-size:16px;font-weight:700;width:100%;margin-top:14px;cursor:pointer}
button:disabled{opacity:.5;cursor:wait}
#msg{margin-top:12px;font-size:14px;min-height:20px}#msg.err{color:#ff7b7b}#msg.ok{color:#7be3a8}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:20px}
.feat{background:#0f1319;border:1px solid var(--line);border-radius:12px;padding:14px;font-size:14px}.feat b{display:block;margin-bottom:4px}
.feat span{color:var(--mut)}.foot{color:var(--mut);font-size:13px;text-align:center;margin-top:28px}.foot a{color:var(--mut)}
@media(max-width:560px){.grid{grid-template-columns:1fr}.hero h1{font-size:30px}.row{flex-direction:column}}
</style></head><body><div class="wrap">
<div class="hero"><h1>PDF to <span>EPUB</span></h1><p>Real chapters + table of contents for Kindle, Kobo, Apple Books. Free, no signup.</p></div>
<div class="card">
<div id="drop"><b>Drop PDF here or click to choose</b><div id="fname">PDF up to 50MB, 500 pages</div></div>
<input id="file" type="file" accept=".pdf" hidden>
<div class="row"><input id="title" placeholder="Title (optional)" maxlength="120"><input id="author" placeholder="Author (optional)" maxlength="120"></div>
<button id="go">Convert to EPUB</button>
<div id="msg"></div>
</div>
<div class="grid">
<div class="feat"><b>Real chapters</b><span>Headings detected, TOC built, headers/footers stripped.</span></div>
<div class="feat"><b>Private</b><span>In-memory only. Deleted after download. <a href="/privacy" style="color:#9aa4b5">Privacy</a>.</span></div>
<div class="feat"><b>Kindle-ready</b><span>Send via Send-to-Kindle or copy over USB.</span></div>
<div class="feat"><b>Free text PDFs</b><span>Scans need OCR — clear error, Calibre fallback on server.</span></div>
</div>
<div class="foot">No account · No watermark · <span id="st"></span></div>
</div><script>
const drop=document.getElementById('drop'),fi=document.getElementById('file'),fn=document.getElementById('fname'),msg=document.getElementById('msg'),go=document.getElementById('go');
drop.onclick=()=>fi.click();
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.add('over')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.remove('over')}));
drop.addEventListener('drop',x=>{fi.files=x.dataTransfer.files;show()});
fi.onchange=show;
function show(){if(fi.files[0])fn.textContent=fi.files[0].name+' · '+(fi.files[0].size/1048576).toFixed(1)+'MB'}
go.onclick=async()=>{
 if(!fi.files[0]){msg.className='err';msg.textContent='Choose a PDF first.';return}
 msg.className='';msg.textContent='Converting…';go.disabled=true;
 const fd=new FormData();fd.append('f',fi.files[0]);fd.append('title',document.getElementById('title').value);fd.append('author',document.getElementById('author').value);
 try{const r=await fetch('/convert',{method:'POST',body:fd});
 if(!r.ok){const t=await r.text();throw new Error(r.status+': '+t.slice(0,140))}
 const b=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(b);
 a.download=(fi.files[0].name||'book').replace(/\\.pdf$/i,'')+'.epub';a.click();
 msg.className='ok';msg.textContent='Done — EPUB downloaded.'}catch(e){msg.className='err';msg.textContent=e.message}
 go.disabled=false};
fetch('/stats').then(r=>r.json()).then(s=>{document.getElementById('st').textContent=s.conversions_ok+' books converted'}).catch(()=>{});
</script></body></html>"""

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
