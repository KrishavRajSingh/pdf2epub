"""PDF -> EPUB MVP. Free text-only. No auth, no DB, no storage."""
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import pymupdf
from ebooklib import epub
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
import time

app = FastAPI()
MAX_MB = 200  # ponytail: launched at 50, scan crowd files run bigger; raise when paid
MAX_PAGES = 500  # ponytail: cap keeps free tier fast, raise when paid
OCR_MAX_PAGES = 200  # ponytail: sync OCR ~2-5 req-min this size, queue (RQ) when bigger scans show up
LOG = Path(os.environ.get("LOG_DIR", ".")) / "conversions.log"  # ponytail: on Railway set LOG_DIR=/data + volume, else dies with container
_HITS: dict[str, list[float]] = {}  # ponytail: in-mem throttle, redis when paid

def log(ok: bool, pages: int, kb_in: int, kb_out: int, err: str = "", ref: str = "", email: str = ""):
    try:
        if LOG.exists() and LOG.stat().st_size > 1_000_000:
            LOG.write_text("")  # ponytail: rotate by trunc, log shipper when paid
        with LOG.open("a") as fh:
            fh.write(json.dumps({"t": datetime.now(timezone.utc).isoformat(),
                "ok": ok, "pages": pages, "in": kb_in, "out": kb_out, "err": err[:80],
                "ref": ref[:60], "email": email}) + "\n")
    except OSError:
        pass  # ponytail: analytics never breaks conversion

def ref_of(request: Request) -> str:
    # ponytail: reddit sends origin-only referer, ?s= tag distinguishes which post
    s = request.query_params.get("s", "")
    r = (request.headers.get("referer") or "")[:40]
    return f"{s}|{r}" if s or r else ""

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

def ocr_doc(doc) -> list[str] | None:
    # ponytail: 300dpi render + tesseract CLI, same subprocess pattern as calibre; swap engine if quality complaints
    if not shutil.which("tesseract"):
        return None
    out = []
    for page in doc:
        try:
            png = page.get_pixmap(dpi=300).tobytes("png")
            r = subprocess.run(["tesseract", "stdin", "stdout", "-l", "eng"],
                input=png, capture_output=True, timeout=60)
            out.append(r.stdout.decode("utf-8", "replace") if r.returncode == 0 else "")
        except Exception:
            out.append("")
    return out

def ocr_chapters(pages: list[str]):
    """Tesseract text -> same (kind, text) rows the text path emits."""
    # ponytail: paragraphs = tesseract blank-line blocks, headings by keyword/CAPS — no layout model needed for prose
    chapters, cur = [], []

    def flush():
        if cur:
            chapters.append(cur.copy())
            cur.clear()

    for txt in pages:
        for para in re.split(r"\n\s*\n", txt):
            lines = [l.strip() for l in para.splitlines() if l.strip()]
            if not lines:
                continue
            text = " ".join(lines)
            head = re.match(r"^(chapter|part|prologue|epilogue|book)\b", text, re.I) or (
                text.isupper() and len(text) <= 60 and any(c.isalpha() for c in text))
            if head and len(text) < 120:
                flush()
                cur.append(("h1", text))
            else:
                cur.append(("p", text))
    flush()
    return chapters

def build_epub(chapters, title: str, author: str) -> bytes:
    book = epub.EpubBook()
    book.set_title(title)
    if author:
        book.add_author(author)
    book.set_language("en")
    items, toc = [], []
    for i, ch in enumerate(chapters or [[("p", "empty")]]):
        # ponytail: TOC label = the chapter's own heading, else the Kindle menu shows "ch1", "ch2"
        name = next((t for k, t in ch if k in ("h1", "h2")), f"ch{i+1}")
        c = epub.EpubHtml(title=name[:120], file_name=f"ch{i+1}.xhtml")
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
    return buf.getvalue()

PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PDF to EPUB — free, real chapters for Kindle</title>
<meta name="description" content="Free PDF to EPUB with real chapters and TOC for Kindle/Kobo/Apple Books. Text and scanned PDFs (OCR beta), no signup, files deleted after download.">
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
<div id="drop"><b>Drop PDF here or click to choose</b><div id="fname">PDF up to 200MB, 500 pages</div></div>
<input id="file" type="file" accept=".pdf" hidden>
<div class="row"><input id="title" placeholder="Title (optional)" maxlength="120"><input id="author" placeholder="Author (optional)" maxlength="120"></div>
<div class="row"><input id="email" placeholder="Email (optional) - only for the paid tier launch and big files" maxlength="120"></div>
<button id="go">Convert to EPUB</button>
<button id="sample" style="background:#0f1319;border:1px solid var(--line);color:var(--txt);font-weight:600;margin-top:10px">Try it with a sample PDF</button>
<div id="msg"></div>
</div>
<div class="grid">
<div class="feat"><b>Real chapters</b><span>Headings detected, TOC built, headers/footers stripped.</span></div>
<div class="feat"><b>Private</b><span>In-memory only. Deleted after download. <a href="/privacy" style="color:#9aa4b5">Privacy</a>.</span></div>
<div class="feat"><b>Kindle-ready</b><span>Send via Send-to-Kindle or copy over USB.</span></div>
<div class="feat"><b>Scanned books (beta)</b><span>OCR reads book scans up to 200 pages into searchable text.</span></div>
</div>
<div class="feat" style="margin-top:12px"><b>What you get</b><span>One paragraph per paragraph (not one per printed line), running headers and page numbers stripped, headings turned into chapters, and a clickable table of contents. The sample button converts a 4 page PDF so you can check it in 5 seconds.</span></div>
<div class="foot">No account · No watermark · <span id="st"></span></div>
</div><script>
const drop=document.getElementById('drop'),fi=document.getElementById('file'),fn=document.getElementById('fname'),msg=document.getElementById('msg'),go=document.getElementById('go'),smp=document.getElementById('sample');
drop.onclick=()=>fi.click();
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.add('over')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.remove('over')}));
drop.addEventListener('drop',x=>{fi.files=x.dataTransfer.files;show()});
fi.onchange=show;
function show(){if(fi.files[0])fn.textContent=fi.files[0].name+' · '+(fi.files[0].size/1048576).toFixed(1)+'MB'}
go.onclick=async()=>{
 if(!fi.files[0]){msg.className='err';msg.textContent='Choose a PDF first.';return}
 msg.className='';msg.textContent='Converting…';go.disabled=true;
 const fd=new FormData();fd.append('f',fi.files[0]);fd.append('title',document.getElementById('title').value);fd.append('author',document.getElementById('author').value);fd.append('email',document.getElementById('email').value);
 try{const r=await fetch('/convert',{method:'POST',body:fd});
 if(!r.ok){const t=await r.text();throw new Error(r.status+': '+t.slice(0,140))}
 const b=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(b);
 a.download=(fi.files[0].name||'book').replace(/\\.pdf$/i,'')+'.epub';a.click();
 msg.className='ok';msg.textContent='Done — EPUB downloaded.'}catch(e){msg.className='err';msg.textContent=e.message}
 go.disabled=false};
smp.onclick=async()=>{
 msg.className='';msg.textContent='Converting the sample…';smp.disabled=true;go.disabled=true;
 try{
  const b=await (await fetch('/sample.pdf')).blob();
  const fd=new FormData();fd.append('f',new File([b],'sample.pdf',{type:'application/pdf'}));
  fd.append('title','Sample Book');fd.append('email',document.getElementById('email').value);
  const r=await fetch('/convert',{method:'POST',body:fd});
  if(!r.ok){const t=await r.text();throw new Error(r.status+': '+t.slice(0,140))}
  const blob=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='sample.epub';a.click();
  msg.className='ok';msg.textContent='Done. Open sample.epub in Kindle or Apple Books and check the chapter list.'}
 catch(e){msg.className='err';msg.textContent=e.message}
 smp.disabled=false;go.disabled=false};
fetch('/stats').then(r=>r.json()).then(s=>{document.getElementById('st').textContent=s.conversions_ok+' books converted'}).catch(()=>{});
</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    try:
        with LOG.open("a") as fh:  # ponytail: visit line, no PII, ref tag only
            fh.write(json.dumps({"t": datetime.now(timezone.utc).isoformat(), "visit": 1, "ref": ref_of(request)}) + "\n")
    except OSError:
        pass
    return PAGE

@app.get("/sample.pdf")
def sample_pdf():
    # ponytail: generated on the fly, no binary in repo. Shows the three things we claim:
    # wrapped lines joined into one paragraph, running header + page number dropped, chapters detected.
    doc = pymupdf.open()
    body = ("This is a sample PDF so you can try the converter without hunting for a file. "
            "If this comes out as one clean paragraph in your reader, the converter joined the "
            "printed lines back together and dropped the running header.")
    for i, (head, text) in enumerate([
        ("Chapter One", body),
        ("Chapter Two", body + " The second chapter repeats the text on purpose, so you can see two entries in the table of contents."),
    ]):
        page = doc.new_page()
        page.insert_text((72, 60), "Sample Book - a running header", fontsize=9, color=(0.45, 0.45, 0.45))
        page.insert_text((72, 120), head, fontsize=22)
        page.insert_textbox(pymupdf.Rect(72, 150, 520, 420), text, fontsize=11)
        page.insert_text((300, 780), str(i + 1), fontsize=9)
    data = doc.tobytes()
    doc.close()
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=sample.pdf"})

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/favicon.ico")
def favicon():
    return HTMLResponse("", status_code=204)

@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    return ("<h1>Privacy</h1><p>Files processed in memory, never stored. Counts (pages, bytes) logged to conversions.log. "
            "If you type an email we keep it in the same log, used only to contact you about the paid tier and to email you a file "
            "if a conversion needs a queue. No accounts, no third party analytics, nothing resold.</p><p><a href='/'>back</a></p>")

@app.get("/stats")
def stats():
    # ponytail: totals from log file, no DB/dashboard lib
    ok = fail = pages = visits = ocr = scan_fail = emails = 0
    refs: dict[str, int] = {}
    ok_by_ref: dict[str, int] = {}
    try:
        for line in LOG.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("visit"):
                visits += 1
                key = r.get("ref") or "direct"
                refs[key] = refs.get(key, 0) + 1
                continue
            ok += bool(r.get("ok"))
            fail += not r.get("ok")
            pages += int(r.get("pages", 0))
            c = r.get("err", "")
            ocr += bool(r.get("ok")) and c == "ocr"
            scan_fail += (not r.get("ok")) and c.startswith("scan")
            emails += 1 if r.get("email") else 0
            if r.get("ok"):  # ponytail: per-launch-post measurement, ref tag before the pipe
                key = (r.get("ref") or "direct").split("|")[0] or "direct"
                ok_by_ref[key] = ok_by_ref.get(key, 0) + 1
    except OSError:
        pass
    top = dict(sorted(refs.items(), key=lambda kv: -kv[1])[:10])
    top_ok = dict(sorted(ok_by_ref.items(), key=lambda kv: -kv[1])[:10])
    return {"visits": visits, "refs": top, "conversions_ok": ok, "ocr_ok": ocr,
            "failed": fail, "scan_fail": scan_fail, "pages": pages, "ok_by_ref": top_ok,
            "emails_captured": emails}

def _join(lines):
    """Join the wrapped lines of one paragraph; drop the hyphen at a line break."""
    out = ""
    for ln in lines:
        if not out:
            out = ln
        elif out.endswith("-"):
            out = out[:-1] + ln
        else:
            out += " " + ln
    return re.sub(r"\s+", " ", out).strip()


def _blocks(doc):
    """Yield (page_no, y0, size, text) per text block, lines joined into one paragraph.

    ponytail: a visual line is not a paragraph. One wrapped paragraph came out as one
    <p> per line, which is exactly the "break paragraphs weird" complaint. PDF blocks
    are the paragraph unit, so join inside the block.
    """
    for i, page in enumerate(doc):
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            lines, size = [], 0.0
            for line in b.get("lines", []):
                txt = "".join(s["text"] for s in line["spans"]).strip()
                if not txt:
                    continue
                lines.append(txt)
                size = max(size, max(s["size"] for s in line["spans"]))
            if not lines:
                continue
            yield i, b["bbox"][1], round(size, 1), _join(lines)

@app.post("/convert")
async def convert(request: Request, f: UploadFile = File(...), title: str = Form(""), author: str = Form(""), email: str = Form("")):
    throttle(request)
    ref = ref_of(request)
    raw = await f.read()
    kb_in = len(raw) // 1024
    if len(raw) > MAX_MB * 1024 * 1024:
        log(False, 0, kb_in, 0, "too big", ref)
        raise HTTPException(413, f"over {MAX_MB}MB in v1")
    if not (f.filename or "").lower().endswith(".pdf") or not raw.startswith(b"%PDF"):
        raise HTTPException(400, "PDF only in v1")
    try:
        doc = pymupdf.open(stream=raw, filetype="pdf")
    except Exception:
        log(False, 0, kb_in, 0, "unreadable pdf", ref)
        raise HTTPException(400, "unreadable PDF")
    if doc.needs_pass:
        doc.close()
        log(False, 0, kb_in, 0, "encrypted pdf", ref)
        raise HTTPException(400, "this PDF is password protected, remove the password and upload it again")
    if len(doc) > MAX_PAGES:
        n0 = len(doc)
        doc.close()
        log(False, n0, kb_in, 0, "too many pages", ref)
        raise HTTPException(413, f"over {MAX_PAGES} pages in v1")

    blocks = list(_blocks(doc))
    npages = len(doc)
    safe_title = (title or (f.filename or "book").rsplit(".", 1)[0])[:120] or "book"
    if not blocks:
        # scanned PDF: OCR is the only thing that helps before falling back
        if npages <= OCR_MAX_PAGES:
            pages_txt = ocr_doc(doc)
            if pages_txt and sum(len(t) for t in pages_txt) > 200:
                data = build_epub(ocr_chapters(pages_txt), safe_title, author[:120])
                log(True, npages, kb_in, len(data) // 1024, "ocr", ref)
                doc.close()
                return StreamingResponse(BytesIO(data), media_type="application/epub+zip",
                    headers={"Content-Disposition": "attachment; filename=book.epub"})
        # ponytail: calibre still last resort (image-only epub beats error)
        doc.close()
        fb = calibre_convert(raw)
        if fb:
            log(True, npages, kb_in, len(fb) // 1024, "calibre-fallback", ref)
            return StreamingResponse(BytesIO(fb), media_type="application/epub+zip",
                headers={"Content-Disposition": "attachment; filename=book.epub"})
        big = npages > OCR_MAX_PAGES
        log(False, npages, kb_in, 0, "scan-over-ocr-cap" if big else "scan-no-text", ref)
        raise HTTPException(422, f"scanned PDF — OCR beta caps at {OCR_MAX_PAGES} pages ({npages} here)"
            if big else "scanned PDF — OCR found no readable text (photo of handwriting?)")
    long = [sz for _, _, sz, t in blocks if len(t) > 40]
    body = Counter(long).most_common(1)[0][0] if long else Counter(sz for _, _, sz, _ in blocks).most_common(1)[0][0]
    h1_cut = body * 1.3
    h2_cut = body * 1.12

    # strip repeated header/footer: same text on >50% pages at top/bottom edge
    ph = doc[0].rect.height
    tops = Counter(t for p, y, sz, t in blocks if y < 60)
    bots = Counter(t for p, y, sz, t in blocks if y > ph - 60)
    n = len(doc)
    banned = {t for t, c in list(tops.items()) + list(bots.items()) if c > n * 0.5}

    chapters, cur = [], []
    def flush():
        if cur:
            chapters.append(cur.copy())
            cur.clear()
    for _, _, sz, t in blocks:
        if t in banned or re.fullmatch(r"[\d\s.\-–—]+", t):
            continue  # ponytail: page numbers/running heads dropped, no config
        if sz >= h1_cut and len(t) < 120:
            flush()
            cur.append(("h1", t))
        elif sz >= h2_cut and len(t) < 120:
            flush()
            cur.append(("h2", t))
        else:
            cur.append(("p", t))
    flush()

    data = build_epub(chapters, safe_title, author[:120])
    # ponytail: nothing stored, files die with request — matches their privacy pitch for free
    log(True, npages, kb_in, len(data) // 1024, "", ref, email.strip()[:120])
    doc.close()
    return StreamingResponse(BytesIO(data), media_type="application/epub+zip",
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
