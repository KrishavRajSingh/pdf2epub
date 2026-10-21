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
try:
    from guides import GUIDES, INDEX_BODY
except Exception:  # ponytail: a missing file must not take the site down
    GUIDES, INDEX_BODY = {}, "<p>Guides are unavailable right now.</p>"
import time

app = FastAPI()
MAX_MB = 200  # ponytail: launched at 50, scan crowd files run bigger; raise when paid
MAX_PAGES = 500  # ponytail: cap keeps free tier fast, raise when paid
OCR_MAX_PAGES = 200
OCR_DPI = 200  # ponytail: 300 was 2x the cpu for no readable gain on print; trial credit is scarce
SCAN_MAX_PAGES = 60  # ponytail: 60 phone photos per batch keeps OCR under a couple of minutes  # ponytail: sync OCR ~2-5 req-min this size, queue (RQ) when bigger scans show up
LOG = Path(os.environ.get("LOG_DIR", ".")) / "conversions.log"  # ponytail: on Railway set LOG_DIR=/data + volume, else dies with container
_HITS: dict[str, list[float]] = {}  # ponytail: in-mem throttle, redis when paid

def log(ok: bool, pages: int, kb_in: int, kb_out: int, err: str = "", ref: str = "", email: str = "",
        request: Request = None):
    line = json.dumps({"t": datetime.now(timezone.utc).isoformat(),
        "ok": ok, "pages": pages, "in": kb_in, "out": kb_out, "err": err[:80],
        "ref": ref[:60], "email": email, "ua": ua_of(request)[:120] if request else ""})
    try:
        if LOG.exists() and LOG.stat().st_size > 1_000_000:
            LOG.write_text("")  # ponytail: rotate by trunc, log shipper when paid
        with LOG.open("a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass  # ponytail: analytics never breaks conversion
    print(line, flush=True)  # ponytail: stdout copy so the counters survive a host move (no volume)

def ref_of(request: Request) -> str:
    # ponytail: reddit sends origin-only referer, ?s= tag distinguishes which post
    s = request.query_params.get("s", "")
    r = (request.headers.get("referer") or "")[:80]
    if not s:
        # ponytail: the tag lives on the landing page url, the convert POST carries it in referer
        m = re.search(r"[?&]s=([^&#]+)", r)
        if m:
            s = m.group(1)
    return f"{s}|{r}" if s or r else ""

BOT_UA = re.compile(r"bot|crawl|spider|slurp|curl|wget|python-requests|httpclient|scrapy|"
                     r"headless|phantom|facebookexternalhit|embedly|quora link preview|"
                     r"whatsapp|telegrambot|discordbot|twitterbot|linkedinbot|applebot|"
                     r"ahrefs|semrush|mj12|dotbot|petal|bytespider|gptbot|ccbot|perplexity", re.I)


def ua_of(request: Request) -> str:
    return request.headers.get("user-agent") or ""


def is_bot(ua: str) -> bool:
    if not ua:
        return True  # ponytail: no user agent = not a browser
    return bool(BOT_UA.search(ua))


def throttle(request: Request, limit: int = 10, window: int = 60, day_limit: int = 30):
    # ponytail: day cap so one script cannot burn the trial credit overnight
    # ponytail: behind railway request.client.host is the rotating proxy ip, so the day cap never fired
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (request.client.host if request.client else "?")
    now = time.time()
    hits = [t for t in _HITS.get(ip, []) if now - t < window]
    day = [t for t in _HITS.get(ip, []) if now - t < 86400]
    if len(hits) >= limit:
        raise HTTPException(429, "too many converts, wait a minute")
    if len(day) >= day_limit:
        raise HTTPException(429, "30 conversions a day from this connection, try later")
    hits.append(now)
    day.append(now)
    _HITS[ip] = day

def err_page(msg: str, code: int):
    # ponytail: the cap rejections are where the paid tier gets pitched, so keep the mail link
    return HTMLResponse(f"<h1>{code}</h1><p>{html.escape(msg)}</p>"
        "<p>Too big for the free converter? Email it to me and I'll convert it by hand: "
        "<a href='mailto:krishavrajsingh@gmail.com?subject=PDF%20to%20EPUB'>krishavrajsingh@gmail.com</a></p>"
        "<p><a href='/'>back</a></p>", status_code=code)

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
            png = page.get_pixmap(dpi=OCR_DPI).tobytes("png")
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

def _clean(t: str) -> str:
    # ponytail: PDF text can carry control chars, lxml refuses them in XML -> 500 on a good file
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t or "")


def build_epub(chapters, title: str, author: str) -> bytes:
    book = epub.EpubBook()
    book.set_title(_clean(title)[:120])
    if author:
        book.add_author(_clean(author)[:120])
    book.set_language("en")
    items, toc = [], []
    for i, ch in enumerate(chapters or [[("p", "empty")]]):
        # ponytail: TOC label = the chapter's own heading, else the Kindle menu shows "ch1", "ch2"
        name = next((t for k, t in ch if k in ("h1", "h2")), f"ch{i+1}")
        c = epub.EpubHtml(title=_clean(name)[:120], file_name=f"ch{i+1}.xhtml")
        c.content = "".join(
            f"<h1>{html.escape(_clean(t))}</h1>" if k == "h1" else f"<h2>{html.escape(_clean(t))}</h2>" if k == "h2" else f"<p>{html.escape(_clean(t))}</p>"
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

PAGE_CSS = """
:root{--bg:#0a0c10;--panel:#12151c;--panel2:#171b24;--line:#242a36;--line2:#2f3644;
--txt:#eef1f7;--dim:#98a1b3;--faint:#6b7488;--acc:#8b6cff;--acc2:#a98fff;--ok:#5fd39a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
-webkit-font-smoothing:antialiased}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.wrap{max-width:940px;margin:0 auto;padding:0 20px 72px}
a{color:var(--acc2)}
header.top{display:flex;align-items:center;justify-content:space-between;gap:16px;
padding:22px 0 8px;border-bottom:1px solid var(--line)}
.mark{display:flex;align-items:baseline;gap:9px;font-weight:700;letter-spacing:-.2px;font-size:17px}
.mark .dot{width:9px;height:9px;border-radius:50%;background:var(--acc);box-shadow:0 0 14px var(--acc)}
.mark .to{color:var(--faint);font-weight:500;font-size:15px}
.pill{font-size:12px;color:var(--dim);border:1px solid var(--line);border-radius:99px;padding:5px 11px}
.pill b{color:var(--ok);font-weight:600}
h1{font-size:clamp(30px,6.2vw,52px);line-height:1.05;letter-spacing:-1.6px;margin:34px 0 0;font-weight:760}
h1 .em{color:var(--acc2)}
.lede{color:var(--dim);font-size:clamp(15px,2.2vw,18px);line-height:1.55;margin:16px 0 0;max-width:56ch}
.facts{display:flex;flex-wrap:wrap;gap:8px;margin:22px 0 0}
.fact{font-size:12.5px;color:var(--dim);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
.fact b{color:var(--txt);font-weight:600}
.cta{display:flex;flex-wrap:wrap;gap:10px;margin:26px 0 0}
button,.btn{font:inherit}
.btn{display:inline-flex;align-items:center;gap:9px;border-radius:11px;padding:13px 19px;font-weight:650;
font-size:15px;text-decoration:none;cursor:pointer;border:1px solid transparent}
.btn.primary{background:var(--acc);color:#fff}
.btn.primary:hover{background:#7c5af0}
.btn.ghost{background:var(--panel);border-color:var(--line2);color:var(--txt)}
.btn.ghost:hover{border-color:#3a4252}
.grid2{display:grid;grid-template-columns:1.05fr .95fr;gap:18px;margin-top:34px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:20px}
.card h3{margin:0 0 4px;font-size:15px;letter-spacing:-.1px}
.card .sub{color:var(--faint);font-size:12.5px;margin:0 0 16px}
.drop{border:1.5px dashed #313949;border-radius:13px;padding:30px 18px;text-align:center;cursor:pointer;
transition:.15s;background:#0e1117}
.drop:hover,.drop.over{border-color:var(--acc);background:#141020}
.drop b{display:block;font-size:15.5px;margin-bottom:5px}
.drop span{color:var(--faint);font-size:13px}
.row{display:flex;gap:9px;margin-top:12px}
.row input{flex:1;min-width:0;background:#0b0e14;border:1px solid var(--line);color:var(--txt);
border-radius:10px;padding:11px 12px;font:inherit;font-size:14px}
.row input::placeholder{color:#5d6577}
.go{width:100%;margin-top:13px;background:var(--acc);color:#fff;border:0;border-radius:11px;
padding:14px 18px;font:inherit;font-size:15px;font-weight:680;cursor:pointer}
.go:hover{background:#7c5af0}
.go:disabled{opacity:.55;cursor:wait}
.ghost-btn{width:100%;margin-top:9px;background:transparent;border:1px solid var(--line2);color:var(--dim);
border-radius:11px;padding:11px 18px;font:inherit;font-size:13.5px;cursor:pointer}
.ghost-btn:hover{color:var(--txt);border-color:#3a4252}
#msg{margin-top:11px;font-size:13.5px;min-height:20px;color:var(--dim)}
#msg.err{color:#ff8080}#msg.ok{color:var(--ok)}
.proof .rows{margin:0;padding:0;list-style:none;border-top:1px solid var(--line)}
.proof .rows li{display:flex;gap:12px;justify-content:space-between;align-items:baseline;
padding:9px 0;border-bottom:1px solid var(--line);font-size:13.5px}
.proof .rows .k{color:var(--faint)}
.proof .rows .v{color:var(--txt);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;
text-align:right}
.toc{margin:14px 0 0;border:1px solid var(--line);border-radius:11px;overflow:hidden;background:#0c0f15}
.toc .t{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);
padding:9px 12px;border-bottom:1px solid var(--line);background:#0e1117}
.toc ol{margin:0;padding:8px 12px 11px 30px}
.toc li{font-size:13.5px;color:var(--txt);padding:3px 0}
.para{margin:12px 0 0;font-size:13.5px;line-height:1.6;color:var(--dim)}
.para b{color:var(--txt);font-weight:600}
h2{font-size:19px;letter-spacing:-.3px;margin:44px 0 14px}
.fixes{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
@media(max-width:860px){.fixes{grid-template-columns:repeat(2,1fr)}}
@media(max-width:480px){.fixes{grid-template-columns:1fr}}
.fix{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:14px 15px}
.fix b{display:block;font-size:13.8px;line-height:1.35}
.fix .tag{font-size:11px;color:var(--acc2);font-family:ui-monospace,Menlo,monospace;display:block;margin-bottom:6px}
.note-line{color:var(--dim);font-size:13.5px;margin:16px 0 0;max-width:70ch}
.links{display:flex;flex-wrap:wrap;gap:9px;margin-top:16px}
.links a{font-size:13.5px;text-decoration:none;border:1px solid var(--line2);border-radius:9px;
padding:9px 12px;color:var(--dim);background:var(--panel)}
.links a:hover{color:var(--txt);border-color:#3a4252}
footer{margin-top:52px;padding-top:18px;border-top:1px solid var(--line);color:var(--faint);font-size:12.5px;
display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center}
@media(max-width:780px){.grid2{grid-template-columns:1fr}h1{letter-spacing:-1px}}
@media(max-width:560px){header.top{padding:16px 0 4px}.pill{display:none}}
"""

PAGE_HEAD = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PDF to EPUB - real chapters, real paragraphs, free</title>
<meta name="description" content="Free PDF to EPUB with real chapters, a clickable table of contents, scanned books read with OCR. No signup, no watermark, nothing stored.">
<meta property="og:title" content="PDF to EPUB - real chapters, real paragraphs, free">
<meta property="og:description" content="No signup, no watermark, nothing stored. Scans read with OCR.">
<style>__CSS__</style></head><body><div class="wrap">
<header class="top">
  <div class="mark"><span class="dot"></span>pdf2epub<span class="to mono">/ epub.ftak.net</span></div>
  <div class="pill mono">files not stored &middot; <b>no account</b></div>
</header>

<h1>Your PDF, as a <span class="em">real book</span>.</h1>
<p class="lede">Paragraphs stay paragraphs, headers and page numbers go, headings become chapters.
Free, no signup, nothing kept.</p>
<div class="facts mono">
  <span class="fact"><b>200MB</b> / 500 pages</span>
  <span class="fact">OCR on scans, <b>free</b></span>
  <span class="fact">EPUB3, Kindle, Kobo, Apple Books</span>
</div>

<div class="grid2">
  <div class="card">
    <h3>Convert a PDF</h3>
    <p class="sub">Drop a file. The EPUB downloads straight to your device.</p>
    <div id="drop" class="drop"><b>Drop a PDF here</b><span>or click to choose one</span></div>
    <input id="file" type="file" accept=".pdf" hidden>
    <div class="row">
      <input id="title" placeholder="Title (optional)" maxlength="120">
      <input id="author" placeholder="Author (optional)" maxlength="120">
    </div>
    <div class="row"><input id="email" placeholder="Email (optional) - paid tier launch and big files only"></div>
    <button class="go" id="go">Convert to EPUB</button>
    <button class="ghost-btn" id="sample">Try it with a sample PDF</button>
    <div id="msg"></div>
  </div>

  <div class="card proof">
    <h3>What you actually get</h3>
    <p class="sub">This is the real output for a real 2 page PDF, computed on this page.</p>
    <ul class="rows">
      <li><span class="k">Printed lines in the PDF</span><span class="v">__PARAS__</span></li>
      <li><span class="k">Paragraphs in the EPUB</span><span class="v">__EPARAS__</span></li>
      <li><span class="k">Running header + page number</span><span class="v">removed</span></li>
      <li><span class="k">Table of contents</span><span class="v">__TOCN__ entries</span></li>
    </ul>
    <div class="toc"><div class="t">Table of contents</div><ol>__TOC__</ol></div>
    <p class="para">First paragraph of chapter one, as it comes out: <b>__FIRST__</b></p>
  </div>
</div>

<h2>What it repairs</h2>
<div class="fixes">
  <div class="fix"><span class="tag">paragraphs</span><b>One paragraph per paragraph</b></div>
  <div class="fix"><span class="tag">headers</span><b>Headers and page numbers out</b></div>
  <div class="fix"><span class="tag">chapters</span><b>Headings become chapters</b></div>
  <div class="fix"><span class="tag">scans</span><b>Scans get OCR</b></div>
</div>
<p class="note-line">Then read it anywhere: send to Kindle by email with the subject "convert", copy it over
USB, or open it in Apple Books, Kobo, KOReader or PocketBook.</p>

<div class="links">
  <a href="/scan">Scan a physical book with your phone</a>
  <a href="/guides">Guides</a>
  <a href="/guides/send-pdf-to-kindle">Getting a PDF onto a Kindle</a>
  <a href="/guides/pdf-to-epub-vs-calibre">vs Calibre</a>
  <a href="/privacy">Privacy</a>
</div>

<footer>
  <span>No account &middot; no watermark &middot; files deleted after download</span>
  <span class="mono" id="st"></span>
</footer>
</div><script>
const drop=document.getElementById('drop'),fi=document.getElementById('file'),
 msg=document.getElementById('msg'),go=document.getElementById('go'),smp=document.getElementById('sample');
drop.onclick=()=>fi.click();
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.add('over')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.remove('over')}));
drop.addEventListener('drop',x=>{fi.files=x.dataTransfer.files});
go.onclick=async()=>{
 const f=fi.files[0];
 if(!f){msg.className='err';msg.textContent='Choose a PDF first.';return}
 msg.className='';msg.textContent='Converting...';go.disabled=true;
 const fd=new FormData();fd.append('f',f);
 fd.append('title',document.getElementById('title').value);
 fd.append('author',document.getElementById('author').value);
 fd.append('email',document.getElementById('email').value);
 try{
  const r=await fetch('/convert'+location.search,{method:'POST',body:fd});
  if(!r.ok){const t=await r.text();throw new Error(r.status+': '+t.slice(0,140))}
  const b=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(b);
  a.download=(f.name||'book').replace(/\.pdf$/i,'')+'.epub';a.click();
  msg.className='ok';msg.textContent='Done. EPUB downloaded.'}
 catch(e){msg.className='err';msg.textContent=e.message}
 go.disabled=false};
smp.onclick=async()=>{
 msg.className='';msg.textContent='Converting the sample...';smp.disabled=true;go.disabled=true;
 try{
  const b=await (await fetch('/sample.pdf')).blob();
  const fd=new FormData();fd.append('f',new File([b],'sample.pdf',{type:'application/pdf'}));
  fd.append('title','Sample Book');fd.append('email',document.getElementById('email').value);
  const r=await fetch('/convert'+location.search,{method:'POST',body:fd});
  if(!r.ok){const t=await r.text();throw new Error(r.status+': '+t.slice(0,140))}
  const blob=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='sample.epub';a.click();
  msg.className='ok';msg.textContent='Done. Open sample.epub and check the chapter list.'}
 catch(e){msg.className='err';msg.textContent=e.message}
 smp.disabled=false;go.disabled=false};
fetch('/stats').then(r=>r.json()).then(s=>{const el=document.getElementById('st');
 if(s.conversions_ok>=50)el.textContent=s.conversions_ok+' books converted'}).catch(()=>{});
</script></body></html>"""


def _proof() -> dict:
    """Real output for the sample file, computed here, so the page cannot lie."""
    raw = _sample_pdf()
    doc = pymupdf.open(stream=raw, filetype="pdf")
    blocks = list(_blocks(doc))
    printed = sum(1 for _ in blocks)
    chapters = _structure(blocks, doc)
    doc.close()
    paras = [t for ch in chapters for k, t in ch if k == "p"]
    heads = [t for ch in chapters for k, t in ch if k in ("h1", "h2")]
    first = paras[0] if paras else ""
    if len(first) > 180:
        first = first[:180].rsplit(" ", 1)[0] + " ..."
    return {
        "paras": printed,
        "eparas": len(paras),
        "toc": heads,
        "first": first,
    }


def _page() -> str:
    pr = _proof()
    toc = "".join(f"<li>{html.escape(h)}</li>" for h in pr["toc"]) or "<li>no headings detected</li>"
    return (PAGE_HEAD
            .replace("__CSS__", PAGE_CSS)
            .replace("__PARAS__", str(pr["paras"]))
            .replace("__EPARAS__", str(pr["eparas"]))
            .replace("__TOCN__", str(len(pr["toc"])))
            .replace("__TOC__", toc)
            .replace("__FIRST__", html.escape(pr["first"])))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    line = json.dumps({"t": datetime.now(timezone.utc).isoformat(), "visit": 1,
                       "ref": ref_of(request), "ua": ua_of(request)[:120]})
    try:
        with LOG.open("a") as fh:  # ponytail: visit line, no PII, ref tag only
            fh.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)  # ponytail: stdout copy, see log()
    return _page()

SCAN_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scan a book to EPUB - free</title>
<meta name="description" content="Photograph the pages of a book and get an EPUB with chapters and a table of contents. OCR runs on the pages, nothing is stored.">
<style>
:root{--bg:#0f1115;--card:#171b22;--line:#2a3140;--txt:#e8ecf3;--mut:#9aa4b5;--acc:#7c5cff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:620px;margin:0 auto;padding:32px 18px 64px}
h1{font-size:28px;margin:0 0 8px}p.lead{color:var(--mut);margin:0 0 20px;font-size:15px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px}
button{background:var(--acc);color:#fff;border:0;border-radius:10px;padding:14px 20px;font-size:16px;font-weight:700;width:100%;margin-top:14px;cursor:pointer}
button:disabled{opacity:.5;cursor:wait}
input[type=text]{width:100%;background:#0f1319;border:1px solid var(--line);color:var(--txt);border-radius:10px;padding:12px;margin-top:10px}
#msg{margin-top:12px;font-size:14px;min-height:20px;color:var(--mut)}#msg.err{color:#ff7b7b}#msg.ok{color:#7be3a8}
.note{color:var(--mut);font-size:13px;margin-top:18px}a{color:#b9a7ff}
</style></head><body><div class="wrap">
<h1>Scan a book to EPUB</h1>
<p class="lead">Photograph the pages of a physical book. The text gets read with OCR, the pages get
chapters, and you get an EPUB for a Kindle, Kobo or phone. Nothing is stored.</p>
<div class="card">
<input id="file" type="file" accept="image/*" capture="environment" multiple>
<input id="title" type="text" placeholder="Title (optional)">
<button id="go">Convert pages to EPUB</button>
<div id="msg">Up to 60 pages per batch. Clear photos, one page per shot.</div>
</div>
<p class="note">Prefer a PDF you already have? <a href="/">Convert a PDF</a>. Scans are read with OCR,
so expect a few typos in the text, same as any OCR.</p>
<p class="note">Free, no signup, no watermark. The file is deleted after the download.</p>
</div><script>
const fi=document.getElementById('file'),go=document.getElementById('go'),msg=document.getElementById('msg');
go.onclick=async()=>{
 const files=[...fi.files].filter(f=>f.type.startsWith('image/'));
 if(!files.length){msg.className='err';msg.textContent='Pick at least one page photo.';return}
 msg.className='';msg.textContent='Reading '+files.length+' page(s), this takes a minute…';go.disabled=true;
 try{
  const fd=new FormData();files.forEach(f=>fd.append('files',f,f.name));
  fd.append('title',document.getElementById('title').value);
  const r=await fetch('/scan'+location.search,{method:'POST',body:fd});
  if(!r.ok){const t=await r.text();throw new Error(r.status+': '+t.slice(0,140))}
  const b=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='book.epub';a.click();
  msg.className='ok';msg.textContent='Done. Open the EPUB and check the chapter list.'}
 catch(e){msg.className='err';msg.textContent=e.message}
 go.disabled=false};
</script></body></html>"""


@app.get("/scan", response_class=HTMLResponse)
def scan_page():
    return SCAN_PAGE


@app.post("/scan")
async def scan(request: Request, files: list[UploadFile] = File(...), title: str = Form("")):
    # ponytail: phone scan -> OCR -> epub. reuses ocr_doc/ocr_chapters/build_epub, nothing stored.
    throttle(request, limit=6, window=300)
    ref = ref_of(request)
    if len(files) > SCAN_MAX_PAGES:
        raise HTTPException(413, f"max {SCAN_MAX_PAGES} pages per batch")
    doc = pymupdf.open()
    kb_in = 0
    for f in files:
        raw = await f.read()
        kb_in += len(raw) // 1024
        if not raw:
            continue
        try:
            page = doc.new_page(width=1240, height=1754)  # a4 at 150dpi, matches what most phones shoot
            page.insert_image(page.rect, stream=raw)
        except Exception:
            continue
    if doc.page_count == 0:
        doc.close()
        log(False, 0, kb_in, 0, "no images", ref, request=request)
        raise HTTPException(400, "could not read those images")
    npages = doc.page_count
    texts = ocr_doc(doc) or []
    doc.close()
    if not any(len(t) for t in texts):
        log(False, npages, kb_in, 0, "scan-no-text", ref, request=request)
        raise HTTPException(422, "no readable text found, try a clearer photo of the page")
    data = build_epub(ocr_chapters(texts), (title or "Scanned book")[:120], "")
    log(True, npages, kb_in, len(data) // 1024, "scan", ref, request=request)
    return StreamingResponse(BytesIO(data), media_type="application/epub+zip",
        headers={"Content-Disposition": "attachment; filename=book.epub"})


@app.get("/guides", response_class=HTMLResponse)
def guides_index():
    return guide_page("Guides", "Practical guides for converting PDFs to EPUB, scanning books and getting them onto a reader.", INDEX_BODY, "/guides")


@app.get("/guides/{slug}", response_class=HTMLResponse)
def guide(slug: str):
    g = GUIDES.get(slug)
    if not g:
        raise HTTPException(404, "no such guide")
    title, desc, body = g
    return guide_page(title, desc, body, "/guides/" + slug)


@app.get("/sitemap.xml")
def sitemap():
    urls = ["/", "/scan", "/guides"] + ["/guides/" + s for s in GUIDES]
    body = "".join(f"<url><loc>https://epub.ftak.net{u}</loc></url>" for u in urls)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>',
                    media_type="application/xml")


def guide_page(title: str, desc: str, body: str, canonical: str) -> HTMLResponse:
    # ponytail: one template for every guide, no framework
    return HTMLResponse(f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="https://epub.ftak.net{canonical}">
<style>
:root{{--bg:#0f1115;--card:#171b22;--line:#2a3140;--txt:#e8ecf3;--mut:#9aa4b5;--acc:#7c5cff}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.6}}
.wrap{{max-width:720px;margin:0 auto;padding:36px 20px 72px}}
h1{{font-size:30px;margin:0 0 18px;letter-spacing:-.5px}}h2{{font-size:20px;margin:30px 0 8px}}p,li{{color:#cfd6e3}}
code{{background:#0f1319;border:1px solid var(--line);border-radius:6px;padding:1px 5px;font-size:14px}}
a{{color:#b9a7ff}}.cta{{display:inline-block;background:var(--acc);color:#fff;border-radius:10px;padding:13px 20px;font-weight:700;text-decoration:none;margin-top:10px}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;margin-top:26px}}
.foot{{color:var(--mut);font-size:13px;margin-top:34px}}
</style></head><body><div class="wrap">
<h1>{html.escape(title)}</h1>
{body}
<div class="box"><b>Convert a PDF to EPUB</b><br>Free, no signup, real chapters and a table of contents.
<a class="cta" href="/">Open the converter</a></div>
<div class="foot">Other guides: <a href="/guides">all guides</a> · <a href="/scan">scan a physical book</a></div>
</div></body></html>""")


def _sample_pdf() -> bytes:
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
    return data


@app.get("/thanks", response_class=HTMLResponse)
def thanks(request: Request):
    # ponytail: polar success url lands here; log the checkout id so we know which link converted
    cid = (request.query_params.get("checkout_id") or "")[:80]
    line = json.dumps({"t": datetime.now(timezone.utc).isoformat(), "visit": 1,
                       "ref": "thanks", "checkout_id": cid, "ua": ua_of(request)[:120]})
    try:
        with LOG.open("a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)
    return HTMLResponse("""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Thanks - pdf2epub Shelf</title>
<style>:root{--bg:#0a0c10;--card:#12151c;--line:#242a36;--txt:#eef1f7;--dim:#98a1b3;--acc:#8b6cff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.6}
.wrap{max-width:620px;margin:0 auto;padding:56px 20px}
h1{font-size:28px;letter-spacing:-.5px;margin:0 0 12px}p{color:var(--dim);margin:0 0 14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;margin-top:22px}
b{color:var(--txt)}a{color:var(--acc2)}code{font-family:ui-monospace,Menlo,monospace;font-size:14px}</style></head>
<body><div class="wrap">
<h1>You're in.</h1>
<p>Shelf is $10 a month for 1,000 scanned pages, batch conversion of a whole shelf, and the finished
EPUB delivered to your Kindle.</p>
<div class="card">
<p><b>What happens next</b></p>
<p>Send me the PDF (or the scans) and I will convert it and email the EPUB back, usually the same day.
If it is a scan it gets OCR and the text will have the usual OCR typos, and I will say so.</p>
<p>Email it to <code>krishavrajsingh@gmail.com</code> with the book title in the subject line.</p>
<p>Nothing is stored. The file is processed in memory and deleted after the download, same as the
<a href="/">free converter</a>.</p>
</div>
<p>Questions about the plan, or a file that is over 200MB or 500 pages? Same address, I will work
around it.</p>
</div></body></html>""")


@app.get("/sample.pdf")
def sample_pdf():
    return Response(_sample_pdf(), media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=sample.pdf"})

@app.get("/robots.txt")
def robots():
    # ponytail: fastapi does not serve static files, so the rule lives here
    return Response("User-agent: *\nAllow: /\n\nSitemap: https://epub.ftak.net/sitemap.xml\n",
                    media_type="text/plain")


@app.get("/healthz")
@app.get("/health")
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
    uas: dict[str, int] = {}
    visits_bot = visits_human = visits_unknown = 0
    conv_bot = conv_human = 0
    try:
        for line in LOG.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            ua = r.get("ua") or ""
            if r.get("visit"):
                visits += 1
                key = r.get("ref") or "direct"
                refs[key] = refs.get(key, 0) + 1
                if not ua:
                    visits_unknown += 1  # ponytail: older log lines have no ua, do not call them bots
                elif is_bot(ua):
                    visits_bot += 1
                else:
                    visits_human += 1
                short = ua.split(")")[-1].strip()[:48] if ua else "(no user agent)"
                uas[short] = uas.get(short, 0) + 1
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
                if is_bot(ua):
                    conv_bot += 1
                else:
                    conv_human += 1
    except OSError:
        pass
    top = dict(sorted(refs.items(), key=lambda kv: -kv[1])[:10])
    top_ok = dict(sorted(ok_by_ref.items(), key=lambda kv: -kv[1])[:10])
    return {"visits": visits, "refs": top, "conversions_ok": ok, "ocr_ok": ocr,
            "failed": fail, "scan_fail": scan_fail, "pages": pages, "ok_by_ref": top_ok,
            "emails_captured": emails,
            "visits_human": visits_human, "visits_bot": visits_bot,
            "visits_unknown": visits_unknown,
            "conversions_human": conv_human, "conversions_bot": conv_bot,
            "user_agents": dict(sorted(uas.items(), key=lambda kv: -kv[1])[:8])}

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

def _structure(blocks, doc):
    """blocks -> chapters: [[(kind, text), ...], ...]. shared by /convert and the landing proof."""
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
    return chapters


@app.post("/convert")
async def convert(request: Request, f: UploadFile = File(...), title: str = Form(""), author: str = Form(""), email: str = Form("")):
    throttle(request)
    ref = ref_of(request)
    raw = await f.read()
    kb_in = len(raw) // 1024
    if len(raw) > MAX_MB * 1024 * 1024:
        log(False, 0, kb_in, 0, "too big", ref, email.strip()[:120], request=request)
        raise HTTPException(413, f"over {MAX_MB}MB in v1 - email it to krishavrajsingh@gmail.com and I'll convert it by hand")
    if not (f.filename or "").lower().endswith(".pdf") or not raw.startswith(b"%PDF"):
        raise HTTPException(400, "PDF only in v1")
    try:
        doc = pymupdf.open(stream=raw, filetype="pdf")
    except Exception:
        log(False, 0, kb_in, 0, "unreadable pdf", ref, request=request)
        raise HTTPException(400, "unreadable PDF")
    if doc.needs_pass:
        doc.close()
        log(False, 0, kb_in, 0, "encrypted pdf", ref, request=request)
        raise HTTPException(400, "this PDF is password protected, remove the password and upload it again")
    if len(doc) > MAX_PAGES:
        n0 = len(doc)
        doc.close()
        log(False, n0, kb_in, 0, "too many pages", ref, email.strip()[:120], request=request)
        raise HTTPException(413, f"over {MAX_PAGES} pages in v1 - email it to krishavrajsingh@gmail.com and I'll convert it by hand")

    blocks = list(_blocks(doc))
    npages = len(doc)
    safe_title = (title or (f.filename or "book").rsplit(".", 1)[0])[:120] or "book"
    if not blocks:
        # scanned PDF: OCR is the only thing that helps before falling back
        if npages <= OCR_MAX_PAGES:
            pages_txt = ocr_doc(doc)
            if pages_txt and sum(len(t) for t in pages_txt) > 200:
                data = build_epub(ocr_chapters(pages_txt), safe_title, author[:120])
                log(True, npages, kb_in, len(data) // 1024, "ocr", ref, request=request)
                doc.close()
                return StreamingResponse(BytesIO(data), media_type="application/epub+zip",
                    headers={"Content-Disposition": "attachment; filename=book.epub"})
        # ponytail: calibre still last resort (image-only epub beats error)
        doc.close()
        fb = calibre_convert(raw)
        if fb:
            log(True, npages, kb_in, len(fb) // 1024, "calibre-fallback", ref, request=request)
            return StreamingResponse(BytesIO(fb), media_type="application/epub+zip",
                headers={"Content-Disposition": "attachment; filename=book.epub"})
        big = npages > OCR_MAX_PAGES
        log(False, npages, kb_in, 0, "scan-over-ocr-cap" if big else "scan-no-text", ref, request=request)
        raise HTTPException(422, f"scanned PDF — OCR beta caps at {OCR_MAX_PAGES} pages ({npages} here)"
            if big else "scanned PDF — OCR found no readable text (photo of handwriting?)")
    chapters = _structure(blocks, doc)

    data = build_epub(chapters, safe_title, author[:120])
    # ponytail: nothing stored, files die with request — matches their privacy pitch for free
    log(True, npages, kb_in, len(data) // 1024, "", ref, email.strip()[:120], request=request)
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
