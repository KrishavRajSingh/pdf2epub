"""PDF -> EPUB MVP. Free text-only. No auth, no DB, no storage."""
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import csv
import hashlib
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import urllib.request
import pymupdf
from ebooklib import epub
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
try:
    from guides import GUIDES, INDEX_BODY
except Exception:  # ponytail: a missing file must not take the site down
    GUIDES, INDEX_BODY = {}, "<p>Guides are unavailable right now.</p>"
import time

app = FastAPI()
MAX_MB = 200  # ponytail: launched at 50, scan crowd files run bigger; raise when paid
MAX_PAGES = 500  # ponytail: cap keeps free tier fast, raise when paid
OCR_MAX_PAGES = 200
# ponytail: OCR is the expensive work and the real pain, so that is where the wall sits. text PDFs
# stay free to 500 pages; a scan is free to 20 pages, then $5 unlocks the whole book right away
FREE_OCR_PAGES = 20
PAID_OCR_MAX_PAGES = 600  # ponytail: OCR runs inside the request, past this the proxy times out
OCR_DPI = 200  # ponytail: 300 was 2x the cpu for no readable gain on print; trial credit is scarce
SCAN_FIG_DPI = 150  # ponytail: full-page scan at 200dpi is 4k pixels; 150 keeps maps readable and epub smaller
SCAN_MAX_PAGES = 60  # ponytail: 60 phone photos per batch keeps OCR under a couple of minutes  # ponytail: sync OCR ~2-5 req-min this size, queue (RQ) when bigger scans show up
SHELF_URL = "https://buy.polar.sh/polar_cl_1jZLYsY7lODWs2QOnhNALMww3O7if69LL4nRQ1JiNmJ"  # pdf2epub org, verified 200
ONETIME_URL = "https://buy.polar.sh/polar_cl_ORKV379p0AcaC2enSVTF9bL0IhujaIgYdrajV0D3mtc"  # $5 one book, manual, paid before delivery
SHELF_MAIL = "krishavrajsingh@gmail.com"
SHELF_PRODUCT = "8c3386ae-0aea-4dd2-87bc-7735b8af795a"
ONEBOOK_PRODUCT = "c9dd91ab-92b9-4d82-a79d-191bd965cd86"
POLAR_TOKEN = os.environ.get("POLAR_TOKEN", "")  # ponytail: read-only OAT, only orders:read is needed
POLAR_ORDERS = "https://api.polar.sh/v1/orders/"
# ponytail: a paying subscriber gets a key that lifts the per-file ceiling. no accounts, no db:
# the key is a secret string we mail them, they put it in the url as ?k=KEY
SHELF_KEYS = Path(os.environ.get("LOG_DIR", ".")) / "shelf-keys.txt"  # one key per line
PAID = Path(os.environ.get("LOG_DIR", ".")) / "paid-checkouts.txt"  # verified ids, so refresh is free
USED = Path(os.environ.get("LOG_DIR", ".")) / "used-checkouts.txt"  # one-book id + file hash, one book per payment
FUNNEL_KEY = os.environ.get("FUNNEL_KEY", "")  # ponytail: /funnel shows money numbers, so it needs ?k=
SHELF_MAX_PAGES = 2000  # ponytail: the free tier stops at 500, which is what a textbook is
SHELF_MAX_MB = 500
LOG = Path(os.environ.get("LOG_DIR", ".")) / "conversions.log"  # ponytail: on Railway set LOG_DIR=/data + volume, else dies with container
_HITS: dict[str, list[float]] = {}  # ponytail: in-mem throttle, redis when paid


def shelf_key(request: Request) -> str:
    """Return the subscriber's key if the request carries a valid one.

    ponytail: the key rides in the url, so check the query string and the referer, because the
    form posts to /convert + location.search and some clients drop the query on the post.
    """
    k = (request.query_params.get("k") or "").strip()
    if not k:
        m = re.search(r"[?&]k=([0-9A-Za-z_-]{6,64})", (request.headers.get("referer") or "")[:120])
        k = m.group(1) if m else ""
    if not k:
        return ""
    try:
        keys = {ln.split()[-1] for ln in SHELF_KEYS.read_text().splitlines() if ln.split()}
    except OSError:
        return ""
    return k if k in keys else ""


def paid_checkout(cid: str, product_id: str) -> bool:
    """True only if Polar says this checkout succeeded for this product.

    ponytail: no db, so a verified id is appended to a file on the volume. Polar never un-pays a
    checkout, and the file is small (one line per sale). A missing token means no key, not a free one.
    """
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", cid or ""):
        return False
    try:
        for line in PAID.read_text().splitlines():
            if line.split()[:2] == [cid, product_id]:
                return True
    except OSError:
        pass
    if not POLAR_TOKEN:
        return False
    req = urllib.request.Request(POLAR_ORDERS + "?limit=1&checkout_id=" + cid,
                                 headers={"Authorization": "Bearer " + POLAR_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            items = (json.load(r) or {}).get("items") or []
    except Exception:  # ponytail: a polar outage must not 500 the buyer's success page
        return False
    if not items or items[0].get("status") != "paid" or items[0].get("product_id") != product_id:
        return False
    try:
        with PAID.open("a") as fh:
            fh.write(f"{cid} {product_id}\n")
    except OSError:
        pass
    event("paid", None, checkout_id=cid, product=product_id)  # ponytail: once per checkout, the file dedupes
    return True


def onebook_ok(cid: str, digest: str) -> bool:
    """A paid one-book checkout converts one file. Re-running that same file stays free."""
    try:
        for line in USED.read_text().splitlines():
            parts = line.split()
            if parts and parts[0] == cid:
                return parts[1:2] == [digest]
    except OSError:
        pass
    return paid_checkout(cid, ONEBOOK_PRODUCT)


def onebook_use(cid: str, digest: str):
    # ponytail: the file hash, never the file, so "nothing stored" stays true
    try:
        with USED.open("a") as fh:
            fh.write(f"{cid} {digest}\n")
    except OSError:
        pass


def issue_key(checkout_id: str) -> str:
    """Mint a key for a paid checkout, once per checkout id.

    ponytail: no accounts, no db, no polar api call. the key is a random string in a file on the
    volume, and the checkout id is remembered so a refresh of the page does not mint a second one.
    """
    try:
        done = SHELF_KEYS.read_text()
    except OSError:
        done = ""
    m = re.search(rf"^{re.escape(checkout_id)}\s+(\S+)$", done, re.M)
    if m:
        return m.group(1)
    key = secrets.token_urlsafe(15)
    try:
        with SHELF_KEYS.open("a") as fh:
            fh.write(f"{checkout_id} {key}\n")
    except OSError:
        pass
    print(json.dumps({"t": datetime.now(timezone.utc).isoformat(), "key_issued": checkout_id,
                      "ua": ""}), flush=True)
    return key

def _write(line: str):
    try:
        if LOG.exists() and LOG.stat().st_size > 20_000_000:
            # ponytail: keep one old file, the funnel needs more than a day of history
            LOG.replace(LOG.with_suffix(".log.1"))
        with LOG.open("a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass  # ponytail: analytics never breaks conversion
    print(line, flush=True)  # ponytail: stdout copy so the counters survive a host move (no volume)


def vid_of(request: Request | None) -> str:
    # ponytail: a random id the page keeps in localStorage, no cookie, no account. it is what joins
    # a visit to its convert, its paywall and its payment, so the funnel counts people, not hits
    if request is None:
        return ""
    v = request.headers.get("x-v") or request.query_params.get("v") or ""
    return v if re.fullmatch(r"[0-9A-Za-z]{8,40}", v) else ""


def log(ok: bool, pages: int, kb_in: int, kb_out: int, err: str = "", ref: str = "", email: str = "",
        request: Request = None):
    _write(json.dumps({"t": datetime.now(timezone.utc).isoformat(),
        "ok": ok, "pages": pages, "in": kb_in, "out": kb_out, "err": err[:80],
        "ref": ref[:60], "email": email, "ua": ua_of(request)[:120] if request else "",
        "v": vid_of(request)}))


def event(name: str, request: Request | None = None, **fields):
    """One funnel step. `ev` lines are not visits or conversions, /stats skips them."""
    _write(json.dumps({"t": datetime.now(timezone.utc).isoformat(), "ev": name[:40],
        "v": vid_of(request), "ref": ref_of(request)[:60] if request else "",
        "ua": ua_of(request)[:120] if request else "", **fields}))

def ref_of(request: Request) -> str:
    # ponytail: reddit sends origin-only referer, ?s= tag distinguishes which post
    raw = request.headers.get("referer") or ""
    s = request.query_params.get("s", "") or request.query_params.get("utm_source", "")
    if not s:
        # ponytail: newsletter links carry utm_source, and the convert POST keeps the query
        m = re.search(r"[?&](?:s|utm_source)=([^&#]+)", raw)
        if m:
            s = m.group(1)
    r = raw[:80]
    return f"{s}|{r}" if s or r else ""

BOT_UA = re.compile(r"bot|crawl|spider|slurp|curl|wget|python-requests|python-urllib|"
                     r"httpclient|scrapy|headless|phantom|pingwatch|pingdom|uptimerobot|"
                     r"statuscake|betteruptime|facebookexternalhit|embedly|quora link preview|"
                     r"whatsapp|telegrambot|discordbot|twitterbot|linkedinbot|applebot|"
                     r"ahrefs|semrush|mj12|dotbot|petal|bytespider|gptbot|ccbot|perplexity", re.I)


def ua_of(request: Request) -> str:
    return request.headers.get("user-agent") or ""


def is_bot(ua: str) -> bool:
    if not ua:
        return True  # ponytail: no user agent = not a browser
    return bool(BOT_UA.search(ua))


def throttle(request: Request, limit: int = 30, window: int = 60, day_limit: int = 300):
    # ponytail: day cap so one script cannot burn the trial credit overnight
    # ponytail: behind railway request.client.host is the rotating proxy ip, so the day cap never fired
    # ponytail: the real shelf owner did 68 files in 32 min (9/min peak) from one ip, so a 10/min
    # and 30/day cap would have cut that revenue event in half. generous, the page cap is the real limit
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (request.client.host if request.client else "?")
    now = time.time()
    hits = [t for t in _HITS.get(ip, []) if now - t < window]
    day = [t for t in _HITS.get(ip, []) if now - t < 86400]
    if len(hits) >= limit:
        raise HTTPException(429, "too many converts, wait a minute")
    if len(day) >= day_limit:
        raise HTTPException(429, "too many conversions a day from this connection, try later")
    hits.append(now)
    day.append(now)
    _HITS[ip] = day

def err_page(msg: str, code: int):
    # ponytail: the cap rejections are where the paid tier gets pitched, so keep the checkout links
    return HTMLResponse(f"<h1>{code}</h1><p>{html.escape(msg)}</p>"
        "<p>Too big for the free converter? <b>One book:</b> $5 once, then come back and it converts "
        "on the spot, up to 2,000 pages: <a href='/go/onebook?why=errpage'>one book - $5</a>. "
        "<b>A whole shelf:</b> <b>Shelf</b> is $10/month for 1,000 pages, batch conversion of a "
        "whole shelf and delivery to your Kindle: <a href='/go/shelf?why=errpage'>subscribe</a>.</p>"
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

def _ocr_page(page):
    """Render one page and return (text, ink coverage) from Tesseract's TSV output."""
    try:
        pix = page.get_pixmap(dpi=OCR_DPI)
        r = subprocess.run(["tesseract", "stdin", "stdout", "-l", "eng", "tsv"],
            input=pix.tobytes("png"), capture_output=True, timeout=60)
    except Exception:
        return "", 0.0
    if r.returncode != 0:
        return "", 0.0
    lines = {}
    ink = 0
    for row in csv.reader(r.stdout.decode("utf-8", "replace").splitlines(), delimiter="\t"):
        if len(row) < 12 or row[0] != "5" or not row[11].strip():
            continue
        try:
            left, top, width, height = int(row[6]), int(row[7]), int(row[8]), int(row[9])
        except ValueError:
            continue
        lines.setdefault((row[2], row[3], row[4]), []).append((left, row[11].strip()))
        ink += width * height
    paras = [" ".join(t for _, t in sorted(v)) for _, v in
             sorted(lines.items(), key=lambda kv: tuple(int(x) for x in kv[0]))]
    cov = ink / (pix.width * pix.height) if pix.width and pix.height else 0.0
    return "\n\n".join(paras), cov

def ocr_doc(doc, layout: bool = False) -> list | None:
    # ponytail: 200dpi render + tesseract CLI, same subprocess pattern as calibre; swap engine if quality complaints
    if not shutil.which("tesseract"):
        return None
    out = []
    for page in doc:
        text, cov = _ocr_page(page)
        out.append((text, cov) if layout else text)
    return out

def _scan_figures(doc, pages):
    """PNG for low-ink scan pages (maps, plates, tables), so OCR does not turn them into prose."""
    figs = {}
    for i, (text, cov) in enumerate(pages):
        clean = re.sub(r"\s+", " ", text).strip()
        if len(clean) < 3 or cov >= 0.12:
            continue
        if re.match(r"^(chapter|part|prologue|epilogue|book)\b", clean, re.I):
            continue  # keep sparse chapter openers as text so the TOC still gets them
        # A map can OCR into one huge garbage line; very low ink still means picture.
        if len(clean) >= 1800 and cov >= 0.03:
            continue
        figs[i] = doc[i].get_pixmap(dpi=SCAN_FIG_DPI).tobytes("png")
    return figs

def ocr_chapters(pages: list[str], figures: dict | None = None):
    """Tesseract text -> same (kind, text) rows the text path emits."""
    # ponytail: paragraphs = tesseract blank-line blocks, headings by keyword/CAPS — no layout model needed for prose
    chapters, cur = [], []

    def flush():
        if cur:
            chapters.append(cur.copy())
            cur.clear()

    for i, txt in enumerate(pages):
        if figures and i in figures:
            cur.append(("img", (figures[i], "")))
            continue
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
    items, toc, fig_no = [], [], 0
    for i, ch in enumerate(chapters or [[("p", "empty")]]):
        # ponytail: TOC label = the chapter's own heading, else the Kindle menu shows "ch1", "ch2"
        name = next((t for k, t in ch if k in ("h1", "h2")), f"ch{i+1}")
        c = epub.EpubHtml(title=_clean(name)[:120], file_name=f"ch{i+1}.xhtml")
        parts = []
        for k, t in ch:
            if k == "fn":
                continue
            if k == "img":
                png, cap = t if isinstance(t, tuple) else (t, "")
                fig_no += 1
                fn = f"fig{fig_no}.png"
                book.add_item(epub.EpubItem(uid=f"fig{fig_no}", file_name=fn,
                                            media_type="image/png", content=png))
                cap_html = (f'<figcaption style="font-size:.9em;margin-top:.4em">'
                            f'{html.escape(_clean(cap))}</figcaption>') if cap else ""
                parts.append(f'<figure style="text-align:center;margin:1.2em 0">'
                             f'<img src="{fn}" style="max-width:100%;height:auto" '
                             f'alt="Figure from the book"/>{cap_html}</figure>')
            elif k == "h1":
                parts.append(f"<h1>{html.escape(_clean(t))}</h1>")
            elif k == "h2":
                parts.append(f"<h2>{html.escape(_clean(t))}</h2>")
            else:
                parts.append(f"<p>{html.escape(_clean(t))}</p>")
        notes = [t for k, t in ch if k == "fn"]
        if notes:
            # ponytail: notes stay out of the prose and keep their page order; no back-links yet
            parts.append('<div style="margin-top:2.5em;border-top:1px solid #999;padding-top:.5em;font-size:.85em">'
                         '<p style="font-weight:700">Notes</p>'
                         + "".join(f"<p>{html.escape(_clean(t))}</p>" for t in notes) + "</div>")
        c.content = "".join(parts)
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

TRACK_JS = r"""// ponytail: a random id in localStorage joins this visit to its convert, paywall and payment in
// /funnel. no cookie, no account, never sent anywhere but this site
let V='',SRC='direct';
try{V=localStorage.getItem('v')||'';if(!V){V=Math.random().toString(36).slice(2)+Date.now().toString(36);localStorage.setItem('v',V)}}
 catch(e){V=Math.random().toString(36).slice(2)+Date.now().toString(36)}
try{const q=new URLSearchParams(location.search),rf=document.referrer?new URL(document.referrer).hostname:'';
 const now=q.get('s')||q.get('utm_source')||(rf&&rf!==location.hostname?rf.replace(/^www\./,''):'');
 SRC=localStorage.getItem('src')||now||'direct';if(!localStorage.getItem('src'))localStorage.setItem('src',SRC)}catch(e){}
function ev(n,x){try{navigator.sendBeacon('/e',JSON.stringify(Object.assign({n:n,v:V,src:SRC},x||{})))}catch(e){}}
ev('view',{path:location.pathname});
"""

PAGE_CSS = """
:root{--bg:#faf7f0;--panel:#fffdf8;--well:#f4f0e7;--line:#e4ded2;--line2:#d3ccbe;
--txt:#1b1916;--dim:#5b564d;--faint:#6f685b;--acc:#6b4ce6;--acc2:#553bc4;--ok:#1f7a4d;
--serif:"Newsreader",Georgia,"Times New Roman",serif;
--sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
--mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font-family:var(--sans);
-webkit-font-smoothing:antialiased}
::selection{background:#e4dcff;color:var(--txt)}
code,.mono{font-family:var(--mono)}
.wrap{max-width:940px;margin:0 auto;padding:0 20px 72px}
a{color:var(--acc2)}
header.top{display:flex;align-items:center;justify-content:space-between;gap:16px;
padding:24px 0 14px;border-bottom:1px solid var(--line)}
.mark{display:flex;align-items:baseline;gap:9px;font-family:var(--serif);font-weight:500;
letter-spacing:-.2px;font-size:19px}
.mark .dot{width:8px;height:8px;border-radius:50%;background:var(--acc);align-self:center}
.mark .to{color:var(--faint);font-weight:400;font-size:13px;letter-spacing:0}
.pill{font-family:var(--mono);font-size:11.5px;color:var(--dim);border:1px solid var(--line);
border-radius:99px;padding:5px 11px}
.pill b{color:var(--ok);font-weight:500}
h1{font-family:var(--serif);font-size:clamp(30px,4.6vw,42px);line-height:1.1;
letter-spacing:-.02em;margin:30px 0 0;font-weight:400}
h1 .em{color:var(--acc)}
.lede{color:var(--dim);font-size:clamp(15px,1.8vw,16.5px);line-height:1.6;margin:14px 0 0;max-width:54ch}
.facts{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 0}
.fact{font-family:var(--mono);font-size:12px;color:var(--dim);border:1px solid var(--line);
border-radius:4px;padding:6px 10px}
.fact b{color:var(--txt);font-weight:500}
.grid2{display:grid;grid-template-columns:1.05fr .95fr;gap:16px;margin-top:26px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:20px}
.card.convert{display:flex;flex-direction:column}
.card h2{font-family:var(--serif);font-size:14.5px;font-weight:500;margin:0 0 14px;letter-spacing:0}
.drop{border:1.5px dashed var(--line2);border-radius:6px;padding:26px 16px;text-align:center;
cursor:pointer;transition:border-color .15s;background:var(--well)}
.card.convert .drop{flex:1;display:flex;flex-direction:column;justify-content:center}
.drop:hover,.drop.over{border-color:var(--acc)}
.drop b{display:block;font-size:15px;font-weight:600;margin-bottom:4px}
.drop span{color:var(--faint);font-size:12.5px}
.row{display:flex;gap:9px;margin-top:12px}
.row input{flex:1;min-width:0;background:var(--well);border:1px solid var(--line);color:var(--txt);
border-radius:4px;padding:10px 11px;font:inherit;font-size:13px;transition:border-color .15s}
.row input::placeholder{color:var(--faint)}
.row input:hover{border-color:var(--line2)}
.row input:focus-visible{outline:none;border-color:var(--acc)}
.go{width:100%;margin-top:12px;background:var(--acc);color:#fff;border:0;border-radius:6px;
padding:13px 20px;font:inherit;font-size:14.5px;font-weight:700;cursor:pointer;
transition:background .15s}
.go:hover{background:var(--acc2)}
.go:focus-visible{outline:2px solid var(--acc2);outline-offset:2px}
.go:disabled{opacity:.55;cursor:wait}
.ghost-btn{width:100%;margin-top:9px;background:transparent;border:1px solid var(--line2);
color:var(--dim);border-radius:6px;padding:10px 16px;font:inherit;font-size:13px;cursor:pointer;
transition:border-color .15s,color .15s}
.ghost-btn:hover{color:var(--txt);border-color:#bdb4a4}
#msg{margin-top:11px;font-size:13.5px;min-height:20px;color:var(--dim)}
#msg.err{color:#a3301f}#msg.ok{color:var(--ok)}
.proof .rows{margin:0;padding:0;list-style:none;border-top:1px solid var(--line)}
.proof .rows li{display:flex;gap:12px;justify-content:space-between;align-items:baseline;
padding:9px 0;border-bottom:1px solid var(--line);font-size:13px}
.proof .rows .k{color:var(--faint)}
.proof .rows .v{color:var(--txt);font-family:var(--mono);font-size:12px;text-align:right}
.toc{margin:14px 0 0;border:1px solid var(--line);border-radius:4px;overflow:hidden;background:var(--well)}
.toc .t{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;
color:var(--faint);padding:8px 11px;border-bottom:1px solid var(--line)}
.toc ol{margin:0;padding:7px 12px 10px 30px}
.toc li{font-size:13px;padding:2px 0}
.para{margin:12px 0 0;font-size:13px;line-height:1.6;color:var(--dim)}
.para b{color:var(--txt);font-weight:600}
h2{font-family:var(--serif);font-size:19px;font-weight:500;letter-spacing:-.2px;margin:42px 0 14px}
.fixes{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.fix{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:13px 14px}
.fix b{display:block;font-size:13.5px;line-height:1.35;font-weight:600}
.fix .tag{display:block;font-family:var(--mono);font-size:11px;letter-spacing:.06em;
text-transform:uppercase;color:var(--acc);margin-bottom:6px}
.links{display:flex;flex-wrap:wrap;gap:9px;margin-top:34px}
.links a{font-size:13px;text-decoration:none;border:1px solid var(--line2);border-radius:4px;
padding:9px 12px;color:var(--dim);background:var(--panel);transition:border-color .15s,color .15s}
.links a:hover{color:var(--txt);border-color:#bdb4a4}
footer{margin-top:34px;padding-top:16px;border-top:1px solid var(--line);color:var(--faint);
font-size:12.5px;display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center}
footer .mono{font-size:11.5px}
@media(max-width:720px){.grid2{grid-template-columns:1fr}.fixes{grid-template-columns:1fr}
h1{letter-spacing:-.015em}}
@media(max-width:560px){header.top{padding:18px 0 12px}.pill{display:none}.card{padding:16px}}
"""

PAGE_HEAD = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/fonts.css">
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
<p class="lede">Real chapters, real paragraphs. Free, no signup, nothing kept.</p>
<div class="facts mono">
  <span class="fact"><b>200MB</b> / 500 pages</span>
  <span class="fact">Scans: OCR free for <b>__FREEOCR__ pages</b></span>
  <span class="fact">EPUB3, Kindle, Kobo, Apple Books</span>
</div>

<div class="grid2">
  <div class="card convert">
    <h2>Convert a PDF</h2>
    <div id="drop" class="drop"><b>Drop a PDF here</b><span>or click to choose one</span></div>
    <input id="file" type="file" accept=".pdf" hidden>
    <div class="row">
      <input id="title" placeholder="Title (optional)" maxlength="120">
      <input id="author" placeholder="Author (optional)" maxlength="120">
    </div>
    <div class="row"><input id="email" placeholder="Email (optional) - for big files and the paid tier"></div>
    <button class="go" id="go">Convert to EPUB</button>
    <button class="ghost-btn" id="sample">Try it with a sample PDF</button>
    <div id="msg"></div>
  </div>

  <div class="card proof">
    <h2>The actual output</h2>
    <ul class="rows">
      <li><span class="k">Printed lines in the PDF</span><span class="v">__PARAS__</span></li>
      <li><span class="k">Paragraphs in the EPUB</span><span class="v">__EPARAS__</span></li>
      <li><span class="k">Table of contents</span><span class="v">__TOCN__ entries</span></li>
    </ul>
    <div class="toc"><div class="t">Table of contents</div><ol>__TOC__</ol></div>
    <p class="para">First paragraph of chapter one, as it comes out: <b>__FIRST__</b></p>
  </div>
</div>

<h2>What it repairs</h2>
<div class="fixes">
  <div class="fix"><span class="tag">paragraphs</span><b>One paragraph per paragraph</b></div>
  <div class="fix"><span class="tag">chapters</span><b>Headings become chapters</b></div>
  <div class="fix"><span class="tag">scans</span><b>Scans get OCR</b></div>
</div>

<div class="links">
  <a href="/scan">Scan a physical book with your phone</a>
  <a href="/shelf">Shelf: $10/mo, 1,000 pages a month</a>
  <a href="/guides">Guides</a>
  <a href="/privacy">Privacy</a>
</div>

<footer>
  <span>No account &middot; no watermark &middot; files deleted after download</span>
  <span class="mono" id="st"></span>
</footer>
</div><script>
__TRACK__const drop=document.getElementById('drop'),fi=document.getElementById('file'),
 msg=document.getElementById('msg'),go=document.getElementById('go'),smp=document.getElementById('sample');
const BTN='display:inline-block;margin:8px 8px 0 0;background:#6b4ce6;color:#fff;border:0;border-radius:4px;'
 +'padding:10px 16px;font:inherit;font-weight:650;cursor:pointer;text-decoration:none';
const GHOST='display:inline-block;margin:8px 8px 0 0;background:transparent;color:#5b564d;border:1px solid #d3ccbe;'
 +'border-radius:4px;padding:9px 14px;font:inherit;cursor:pointer;text-decoration:none';
function buy(why){return '/go/onebook?why='+why+'&v='+V}
// ponytail: the free converter refuses big files, so the refusal is where the paid tier gets pitched
function pitchPages(n){return 'This PDF has '+(n||'over 500')+' pages. The free converter stops at 500.<br>'
 +'<a style="'+BTN+'" href="'+buy('pages')+'">Convert the whole book - $5</a>'
 +'<a style="'+GHOST+'" href="/go/shelf?why=pages&v='+V+'">A whole shelf? $10/month</a>'
 +'<br><span style="font-size:13px;color:#5b564d">Pay once, you come straight back here and the book converts '
 +'on the spot, up to 2,000 pages. Nothing stored.</span>'
 +'<br><br><span style="font-size:13px;color:#5b564d">Bigger than 2,000 pages? Leave your email for a quote.</span><br>'
 +'<input id="leadmail" type="email" placeholder="your email" '
 +'style="max-width:340px;background:#f4f0e7;border:1px solid #e4ded2;color:#1b1916;'
 +'border-radius:4px;padding:10px 12px;font:inherit;font-size:14px"> '
 +'<button id="leadbtn" style="'+BTN+'">Ask</button>'}
function pitchOcr(n){return 'This is a scan ('+(n||'many')+' pages), so every page has to be read with OCR. '
 +'Free OCR covers __FREEOCR__ pages.<br>'
 +'<a style="'+BTN+'" href="'+buy('ocr')+'">OCR the whole book - $5</a>'
 +'<button id="preview" style="'+GHOST+'">Free: first __FREEOCR__ pages</button>'
 +'<br><span style="font-size:13px;color:#5b564d">Pay once, you come straight back here and the book converts '
 +'on the spot. Nothing stored.</span>'}
document.addEventListener('click',async(e)=>{
 if(e.target.id==='preview'){convert(true);return}
 if(e.target.id!=='leadbtn')return;
 const em=document.getElementById('leadmail');
 if(!em||!em.value)return;
 e.target.disabled=true;ev('lead');
 const fd=new FormData();fd.append('email',em.value);fd.append('reason','cap');
 if(window.capPages)fd.append('pages',window.capPages);
 const r=await fetch('/lead',{method:'POST',body:fd});
 msg.className='ok';msg.innerHTML=r.ok
  ?'Got it. Email the PDF to <a href="mailto:__MAIL__?subject='+encodeURIComponent('PDF to EPUB - '+(window.capName||'book'))+'">__MAIL__</a> with the page count and I will reply with a price.'
  :'Put an email in the box first.';
 e.target.disabled=false;});
drop.onclick=()=>fi.click();
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.add('over')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.remove('over')}));
drop.addEventListener('drop',x=>{fi.files=x.dataTransfer.files;if(fi.files[0])ev('pick')});
fi.addEventListener('change',()=>{if(fi.files[0]){ev('pick');drop.querySelector('b').textContent=fi.files[0].name}});
async function convert(preview){
 const f=fi.files[0];
 if(!f){msg.className='err';msg.textContent='Choose a PDF first.';return}
 msg.className='';msg.textContent=preview?'Reading the first __FREEOCR__ pages...':'Converting...';go.disabled=true;
 ev('submit',preview?{why:'preview'}:{});
 const fd=new FormData();fd.append('f',f);
 fd.append('title',document.getElementById('title').value);
 fd.append('author',document.getElementById('author').value);
 fd.append('email',document.getElementById('email').value);
 if(preview)fd.append('preview','1');
 try{
  const r=await fetch('/convert'+location.search,{method:'POST',body:fd,headers:{'X-V':V}});
  if(!r.ok){const t=await r.text();const er=new Error(r.status+': '+t.slice(0,160));er.status=r.status;throw er}
  const b=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(b);
  a.download=(f.name||'book').replace(/\.pdf$/i,'')+'.epub';a.click();ev('done');
  msg.className='ok';msg.textContent=preview?'Done. The preview EPUB has the first __FREEOCR__ pages.':'Done. EPUB downloaded.'}
 catch(e){msg.className='err';msg.textContent=e.message;ev('fail',{status:String(e.status||'net')});
  const n=+(e.message.match(/\((\d+) here\)/)||[])[1]||0;
  window.capPages=n;window.capName=(f&&f.name)||'book';
  if(e.status===413){msg.className='';msg.innerHTML=pitchPages(n);ev('pitch',{why:'pages'})}
  if(e.status===402&&/scanned/.test(e.message)){msg.className='';msg.innerHTML=pitchOcr(n);ev('pitch',{why:'ocr'})}}
 go.disabled=false}
go.onclick=()=>convert(false);
smp.onclick=async()=>{
 msg.className='';msg.textContent='Converting the sample...';smp.disabled=true;go.disabled=true;ev('sample');
 try{
  const b=await (await fetch('/sample.pdf')).blob();
  const fd=new FormData();fd.append('f',new File([b],'sample.pdf',{type:'application/pdf'}));
  fd.append('title','Sample Book');fd.append('email',document.getElementById('email').value);
  const r=await fetch('/convert'+location.search,{method:'POST',body:fd,headers:{'X-V':V}});
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
    # ponytail: count printed lines, not blocks; "8 lines" from 2 pages reads as a toy
    printed = sum(len(b.get("lines", [])) for pg in doc
                  for b in pg.get_text("dict")["blocks"] if b.get("type") == 0)
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
            .replace("__MAIL__", SHELF_MAIL)
            .replace("__TRACK__", TRACK_JS)
            .replace("__FREEOCR__", str(FREE_OCR_PAGES))
            .replace("__FIRST__", html.escape(pr["first"])))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    line = json.dumps({"t": datetime.now(timezone.utc).isoformat(), "visit": 1,
                       "ref": ref_of(request), "ua": ua_of(request)[:120]})
    _write(line)
    return _page()

SCAN_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/fonts.css">
<title>Scan a book to EPUB - free</title>
<meta name="description" content="Photograph the pages of a book and get an EPUB with chapters and a table of contents. OCR runs on the pages, nothing is stored.">
<style>
:root{--bg:#faf7f0;--card:#fffdf8;--line:#e4ded2;--txt:#1b1916;--mut:#5b564d;--acc:#6b4ce6;--serif:"Newsreader",Georgia,serif;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:620px;margin:0 auto;padding:32px 18px 64px}
h1{font-family:var(--serif);font-weight:500;font-size:28px;margin:0 0 8px}p.lead{color:var(--mut);margin:0 0 20px;font-size:15px}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:22px}
button{background:var(--acc);color:#fff;border:0;border-radius:4px;padding:14px 20px;font-size:16px;font-weight:700;width:100%;margin-top:14px;cursor:pointer}
button:disabled{opacity:.5;cursor:wait}
input[type=text]{width:100%;background:#f4f0e7;border:1px solid var(--line);color:var(--txt);border-radius:4px;padding:12px;margin-top:10px}
.pick{display:block;border:1.5px dashed #d3ccbe;border-radius:6px;background:#f4f0e7;padding:26px 16px;text-align:center;cursor:pointer;transition:border-color .15s}
.pick:hover{border-color:var(--acc)}.pick b{display:block;font-size:15px;margin-bottom:4px}.pick span{color:var(--mut);font-size:12.5px}
#msg{margin-top:12px;font-size:14px;min-height:20px;color:var(--mut)}#msg.err{color:#a3301f}#msg.ok{color:#1f7a4d}
.note{color:var(--mut);font-size:13px;margin-top:18px}a{color:#553bc4}
</style></head><body><div class="wrap">
<h1>Scan a book to EPUB</h1>
<p class="lead">Photograph the pages of a physical book. The text gets read with OCR, map and
figure pages stay as images, and you get an EPUB for a Kindle, Kobo or phone. Nothing is stored.</p>
<div class="card">
<input id="file" type="file" accept="image/*" capture="environment" multiple hidden>
<label class="pick" for="file" id="pick"><b>Choose page photos</b><span>or take them with the camera</span></label>
<input id="title" type="text" placeholder="Title (optional)">
<button id="go">Convert pages to EPUB</button>
<div id="msg">Up to 60 pages per batch. Clear photos, one page per shot.</div>
</div>
<p class="note">Prefer a PDF you already have? <a href="/">Convert a PDF</a>. Scans are read with OCR,
so expect a few typos in the text, same as any OCR.</p>
<p class="note">Free, no signup, no watermark. The file is deleted after the download.</p>
</div><script>
const fi=document.getElementById('file'),go=document.getElementById('go'),msg=document.getElementById('msg');
fi.onchange=()=>{const n=[...fi.files].filter(f=>f.type.startsWith('image/')).length;
 if(n)document.getElementById('pick').innerHTML='<b>'+n+' page'+(n>1?'s':'')+' chosen</b><span>tap to change</span>'};
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
 catch(e){msg.className='err';msg.textContent=e.message;
  if(/^413/.test(e.message))msg.innerHTML=PITCH}
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
    pages = ocr_doc(doc, layout=True) or []
    texts = [t for t, _ in pages]
    if not any(len(t) for t in texts):
        doc.close()
        log(False, npages, kb_in, 0, "scan-no-text", ref, request=request)
        raise HTTPException(422, "no readable text found, try a clearer photo of the page")
    figs = _scan_figures(doc, pages)
    doc.close()
    data = build_epub(ocr_chapters(texts, figs), (title or "Scanned book")[:120], "")
    log(True, npages, kb_in, len(data) // 1024, "scan+fig" if figs else "scan", ref, request=request)
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
    urls = ["/", "/scan", "/shelf", "/guides"] + ["/guides/" + s for s in GUIDES]
    body = "".join(f"<url><loc>https://epub.ftak.net{u}</loc></url>" for u in urls)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>',
                    media_type="application/xml")


def guide_page(title: str, desc: str, body: str, canonical: str) -> HTMLResponse:
    # ponytail: one template for every guide, no framework
    return HTMLResponse(f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/fonts.css">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="https://epub.ftak.net{canonical}">
<style>
:root{{--bg:#faf7f0;--card:#fffdf8;--line:#e4ded2;--txt:#1b1916;--mut:#5b564d;--acc:#6b4ce6;--serif:"Newsreader",Georgia,serif;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.6}}
.wrap{{max-width:720px;margin:0 auto;padding:36px 20px 72px}}
h1{{font-family:var(--serif);font-weight:500;font-size:30px;margin:0 0 18px;letter-spacing:-.02em}}h2{{font-family:var(--serif);font-weight:500;font-size:20px;margin:30px 0 8px}}p,li{{color:#5b564d;max-width:68ch}}
code{{background:#f4f0e7;border:1px solid var(--line);border-radius:6px;padding:1px 5px;font-size:14px}}
a{{color:#553bc4}}.cta{{display:inline-block;background:var(--acc);color:#fff;border-radius:4px;padding:13px 20px;font-weight:700;text-decoration:none;margin-top:10px}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:20px;margin-top:26px}}
.foot{{color:var(--mut);font-size:13px;margin-top:34px}}
.mark{{display:inline-block;font-family:var(--serif);font-weight:500;font-size:19px;text-decoration:none;color:var(--txt);margin-bottom:26px}}.mark .dot{{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--acc);margin-right:9px}}
</style></head><body><div class="wrap">
<a class="mark" href="/"><span class="dot"></span>pdf2epub</a>
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
    chapters = [
        ("Chapter One", [
            "Every book begins with a page that says nothing about the book. The title sits high on the sheet, the author sits under it, and the rest of the page is white space doing quiet work.",
            "This sample file is generated for you, not pulled from a shelf. Convert it and open the result in your reader. If the sentences below arrive as whole paragraphs instead of one line per printed line, the converter did its job.",
            "The running header at the top of this page and the page number at the bottom are the two things a print PDF carries that a reader should never see. Neither one is in the EPUB you get back.",
        ]),
        ("Chapter Two", [
            "A page is a container, not a thought. Words wrap at the margin because paper has an edge, and a converter that treats every wrap as a paragraph break hands you a book that reads like a shopping list.",
            "What a reader wants is the shape the author wrote: paragraphs, headings, chapters. That shape is recoverable. Text blocks in the PDF carry it, and blocks are what this converter reads.",
            "So the second chapter exists to prove the table of contents. Two entries in the file, two entries in the menu of your reader, each one a tap away from where it belongs.",
        ]),
        ("Chapter Three", [
            "Scanned books take a different road. There are no text blocks to read, only pixels, so the pages go through OCR first and the same structure pass runs on the result.",
            "That path is free up to two hundred pages. It is slower, because a machine is reading photographs of paper, but the output is the same EPUB with the same chapters and the same paragraphs.",
            "Nothing you upload is kept. The file is converted in memory, handed back as a download, and gone. No account, no library, no copy on a disk somewhere waiting to be sold.",
        ]),
    ]
    for i, (head, paras) in enumerate(chapters):
        page = doc.new_page()
        page.insert_text((72, 60), "Sample Book - a running header", fontsize=9, color=(0.45, 0.45, 0.45))
        page.insert_text((72, 120), head, fontsize=22)
        y = 158
        for text in paras:
            rect = pymupdf.Rect(72, y, 520, 760)
            # ponytail: no lineheight arg, it makes pymupdf emit one block per line
            left = page.insert_textbox(rect, text, fontsize=11)
            if left < 0:
                break
            y = rect.y1 - left + 14
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
    _write(line)
    # ponytail: hand the subscriber their key here. polar sends the checkout id, so a junk request
    # gets no key. the key is what lifts the per-file ceiling, no account needed.
    key = ""
    if paid_checkout(cid, SHELF_PRODUCT):
        key = issue_key(cid)
    key_html = ""
    if key:
        key_html = (f'<div class="card"><p><b>Your Shelf key</b></p>'
            f'<p>Put this on the end of the converter link and your uploads get the paid limits '
            f'(2,000 pages per file, 500MB):</p>'
            f'<p><code>https://epub.ftak.net/?k={key}</code></p>'
            f'<p>No account, no password. If you lose it, reply to the email I sent you and I will '
            f'send it again.</p></div>')
    elif cid:
        key_html = ('<div class="card"><p><b>Payment not confirmed yet</b></p>'
            '<p>Polar has not shown me a completed payment for this checkout. If you were just '
            f'charged, reply to the Polar receipt and I will send your key.</p></div>')
    return HTMLResponse(f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/fonts.css">
<title>Thanks - pdf2epub Shelf</title>
<style>:root{{--bg:#faf7f0;--card:#fffdf8;--line:#e4ded2;--txt:#1b1916;--dim:#5b564d;--acc:#6b4ce6;--serif:"Newsreader",Georgia,serif;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.6}}
.wrap{{max-width:620px;margin:0 auto;padding:56px 20px}}
h1{{font-family:var(--serif);font-weight:500;font-size:28px;letter-spacing:-.02em;margin:0 0 12px}}p{{color:var(--dim);margin:0 0 14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:20px;margin-top:22px}}
b{{color:var(--txt)}}a{{color:var(--acc)}}code{{font-family:ui-monospace,Menlo,monospace;font-size:14px;word-break:break-all}}.mark{{display:inline-block;font-family:var(--serif);font-weight:500;font-size:17px;text-decoration:none;color:var(--txt);margin-bottom:22px}}.mark .dot{{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--acc);margin-right:8px}}</style></head>
<body><div class="wrap">
<a class="mark" href="/"><span class="dot"></span>pdf2epub</a>
<h1>You're in.</h1>
<p>Shelf is $10 a month for 1,000 pages of your own, no per-file ceiling, batch conversion of a
whole shelf, and the finished EPUB delivered to your Kindle.</p>
{key_html}
<div class="card">
<p><b>What happens next</b></p>
<p>Send me the PDF (or the scans) and I will convert it and email the EPUB back, usually the same day.
If it is a scan it gets OCR and the text will have the usual OCR typos, and I will say so.</p>
<p>Email it to <code>{SHELF_MAIL}</code> with the book title in the subject line.</p>
<p>Nothing is stored. The file is processed in memory and deleted after the download, same as the
<a href="/">free converter</a>.</p>
</div>
<p>Questions about the plan, or a file that is over 500MB? Same address, I will work around it.</p>
</div><script>{TRACK_JS}
ev('return',{{cid:{json.dumps(cid)}}});</script></body></html>""")


@app.get("/onebook", response_class=HTMLResponse)
def onebook(request: Request):
    # ponytail: separate polar success page for the $5 manual conversion, so it never mints a Shelf key
    cid = (request.query_params.get("checkout_id") or "")[:80]
    line = json.dumps({"t": datetime.now(timezone.utc).isoformat(), "visit": 1,
                       "ref": "onebook", "checkout_id": cid, "ua": ua_of(request)[:120]})
    _write(line)
    paid = paid_checkout(cid, ONEBOOK_PRODUCT)
    # ponytail: paid means the upload box right here, converted on the spot. email stays the fallback
    if paid:
        main = f"""<div class="card">
<p><b>Payment confirmed.</b> Choose the PDF and it converts now, up to 2,000 pages, scans included.</p>
<input id="file" type="file" accept=".pdf">
<button class="btn" id="go">Convert my book</button>
<p id="msg"></p>
<p style="font-size:13px">One book per payment. Converting the same file again is free if you need to.
A long scan takes a few minutes, keep this tab open.</p>
</div>
<p>Something wrong with the result? Email <code>{SHELF_MAIL}</code> with the checkout ID
<code>{html.escape(cid)}</code> and I will fix it by hand.</p>"""
    else:
        cid_html = (f"<p>Checkout ID: <code>{html.escape(cid)}</code></p>" if cid else
                    "<p>If you just paid and there is no checkout ID in the address, reply to the Polar receipt.</p>")
        main = f"""<div class="card">
<p><b>Payment not confirmed yet.</b> Polar can take a few seconds, so
<a href="">reload this page</a> first.</p>
<p>Still not confirmed? Email the PDF to <code>{SHELF_MAIL}</code> with the subject <b>One book</b>,
from the email you paid with, and I will convert it by hand and send it back the same day.</p>
{cid_html}
</div>"""
    return HTMLResponse(f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/fonts.css">
<title>One book - pdf2epub</title>
<style>:root{{--bg:#faf7f0;--card:#fffdf8;--line:#e4ded2;--txt:#1b1916;--dim:#5b564d;--acc:#6b4ce6;--serif:"Newsreader",Georgia,serif;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.6}}
.wrap{{max-width:620px;margin:0 auto;padding:56px 20px}}
h1{{font-family:var(--serif);font-weight:500;font-size:28px;letter-spacing:-.02em;margin:0 0 12px}}p{{color:var(--dim);margin:0 0 14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:20px;margin-top:22px}}
.btn{{display:block;width:100%;margin:12px 0;background:var(--acc);color:#fff;border:0;border-radius:6px;padding:13px 20px;font:inherit;font-weight:700;cursor:pointer}}.btn:disabled{{opacity:.55;cursor:wait}}
input[type=file]{{width:100%;font:inherit}}#msg.err{{color:#a3301f}}#msg.ok{{color:#1f7a4d}}
b{{color:var(--txt)}}a{{color:#553bc4}}code{{font-family:ui-monospace,Menlo,monospace;font-size:14px;word-break:break-all}}.mark{{display:inline-block;font-family:var(--serif);font-weight:500;font-size:17px;text-decoration:none;color:var(--txt);margin-bottom:22px}}.mark .dot{{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--acc);margin-right:8px}}</style></head>
<body><div class="wrap">
<a class="mark" href="/"><span class="dot"></span>pdf2epub</a>
<h1>One book.</h1>
<p>Paid once. Nothing is stored: the file is converted in memory and deleted after the download.</p>
{main}
<p><a href="/">Back to the free converter</a></p>
</div><script>{TRACK_JS}
ev('return',{{cid:{json.dumps(cid)}}});
const go=document.getElementById('go'),fi=document.getElementById('file'),msg=document.getElementById('msg');
if(go)go.onclick=async()=>{{
 const f=fi.files[0];if(!f){{msg.className='err';msg.textContent='Choose a PDF first.';return}}
 go.disabled=true;msg.className='';msg.textContent='Converting... a long scan takes a few minutes.';
 const fd=new FormData();fd.append('f',f);
 try{{const r=await fetch('/convert?paid='+encodeURIComponent({json.dumps(cid)}),{{method:'POST',body:fd,headers:{{'X-V':V}}}});
  if(!r.ok)throw new Error(r.status+': '+(await r.text()).slice(0,200));
  const b=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(b);
  a.download=(f.name||'book').replace(/\.pdf$/i,'')+'.epub';a.click();
  msg.className='ok';msg.textContent='Done. EPUB downloaded.'}}
 catch(e){{msg.className='err';msg.textContent=e.message}}
 go.disabled=false}};
</script></body></html>""")


@app.post("/lead")
async def lead(request: Request, email: str = Form(""), pages: int = Form(0), reason: str = Form("")):
    # ponytail: the cap rejection is the moment of intent, so take the email right there
    e = email.strip()[:120]
    if not e:
        return JSONResponse({"ok": False}, status_code=400)
    line = json.dumps({"t": datetime.now(timezone.utc).isoformat(), "ok": False, "pages": pages,
                       "in": 0, "out": 0, "err": "lead:" + reason[:60], "ref": ref_of(request),
                       "email": e, "ua": ua_of(request)[:120]})
    _write(line)
    return {"ok": True}


@app.get("/shelf", response_class=HTMLResponse)
def shelf(request: Request):
    # ponytail: the paid tier needs a linkable page, otherwise only the founder can point people at it
    ref = ref_of(request)
    line = json.dumps({"t": datetime.now(timezone.utc).isoformat(), "visit": 1,
                       "ref": "shelf" + ("|" + ref if ref else ""), "ua": ua_of(request)[:120]})
    _write(line)
    return HTMLResponse(f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/fonts.css">
<title>Shelf - pdf2epub</title>
<meta name="description" content="Shelf: $10/month for 1,000 scanned pages, batch conversion of a whole shelf, and the finished EPUB delivered to your Kindle.">
<link rel="canonical" href="https://epub.ftak.net/shelf">
<style>:root{{--bg:#faf7f0;--card:#fffdf8;--line:#e4ded2;--txt:#1b1916;--dim:#5b564d;--acc:#6b4ce6;--ok:#1f7a4d;--serif:"Newsreader",Georgia,serif;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);
font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.6}}
.wrap{{max-width:640px;margin:0 auto;padding:56px 20px}}
h1{{font-family:var(--serif);font-weight:500;font-size:30px;letter-spacing:-.02em;margin:0 0 10px}}p{{color:var(--dim);margin:0 0 14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:20px;margin-top:22px}}
b{{color:var(--txt)}}a{{color:#553bc4}}code{{font-family:ui-monospace,Menlo,monospace;font-size:14px}}
.btn{{display:inline-block;background:var(--acc);color:#fff;text-decoration:none;border-radius:6px;
padding:13px 20px;font-weight:650;margin-top:8px}}
ul{{color:var(--dim);padding-left:20px}}li{{margin:0 0 6px}}.mark{{display:inline-block;font-family:var(--serif);font-weight:500;font-size:17px;text-decoration:none;color:var(--txt);margin-bottom:22px}}.mark .dot{{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--acc);margin-right:8px}}</style></head>
<body><div class="wrap">
<a class="mark" href="/"><span class="dot"></span>pdf2epub</a>
<h1>Shelf</h1>
<p>The free converter stays free. Shelf is for the people who have a shelf.</p>
<p>One reader put 68 books through the free converter in 32 minutes. Seven of the uploads
hit the 500-page cap. Shelf is for that reader.</p>
<div class="card">
<p><b>$10 a month, included</b></p>
<ul>
<li>1,000 pages a month included. If you go over, email me and we will sort it out.</li>
<li><b>No per-file ceiling.</b> The free converter stops at 500 pages, which is where a textbook
sits. Shelf goes to 2,000 pages per file, so the big ones go through.</li>
<li>Batch by email: send me a shelf of PDFs, get the EPUBs back.</li>
<li>Repair: re-run and fix a conversion as many times as you want.</li>
<li>Send-to-Kindle help: send me the EPUB and your Kindle address, and I will send it on.</li>
<li>Nothing stored. Files are processed in memory and deleted, same as the free tier.</li>
</ul>
<a class="btn" href="/go/shelf?why=shelfpage" data-go>Subscribe - $10/month</a>
</div>
<p><b>What you get when you subscribe:</b> a private key. Put it on the end of
the converter link, like <code>epub.ftak.net/?k=YOURKEY</code>, and your uploads go to the paid
limits. No account, no password, nothing to set up.</p>
<p><b>Batch and Kindle delivery are email-assisted for now.</b> Send the files and your Kindle
address to <a href="mailto:{SHELF_MAIL}?subject=PDF%20to%20EPUB">{SHELF_MAIL}</a>, and I will
send the EPUBs back, usually the same day.</p>
<div class="card">
<p><b>One big book, not a shelf?</b></p>
<p>Pay $5 once. You come straight back to an upload box and the book converts on the spot. Up to
2,000 pages. Scans get OCR.</p>
<a class="btn" href="/go/onebook?why=shelfpage" data-go>One book - $5</a>
</div>
<p>Bigger than 2,000 pages or a rough scan?
<a href="mailto:{SHELF_MAIL}?subject=One-time%20conversion">Email me the page count</a>
and I will quote it.</p>
<p>The <a href="/">free converter</a> handles one PDF up to 200MB and 500 pages, and scans up to
{FREE_OCR_PAGES} pages, with no signup.</p>
</div><script>{TRACK_JS}
document.querySelectorAll('[data-go]').forEach(a=>a.href+='&v='+V);</script></body></html>""")


@app.get("/sample.pdf")
def sample_pdf():
    return Response(_sample_pdf(), media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=sample.pdf"})

@app.get("/robots.txt")
def robots():
    # ponytail: fastapi does not serve static files, so the rule lives here
    return Response("User-agent: *\nAllow: /\n\nSitemap: https://epub.ftak.net/sitemap.xml\n",
                    media_type="text/plain")


FONT_DIR = Path(__file__).parent / "fonts"
FONT_CSS = """@font-face{font-family:Newsreader;src:url(/fonts/newsreader-latin.woff2) format("woff2");
font-weight:400 500;font-style:normal;font-display:swap}
@font-face{font-family:"JetBrains Mono";src:url(/fonts/jetbrainsmono-latin.woff2) format("woff2");
font-weight:400 500;font-style:normal;font-display:swap}
"""


@app.get("/fonts.css")
def fonts_css():
    # ponytail: no static mount, one cached sheet beats repeating @font-face in six templates
    return Response(FONT_CSS, media_type="text/css",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/fonts/{name}")
def font_file(name: str):
    f = FONT_DIR / name
    if f.suffix != ".woff2" or not f.is_file():
        raise HTTPException(404)
    return Response(f.read_bytes(), media_type="font/woff2",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


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
            "if a conversion needs a queue. The page keeps a random id in your browser's localStorage so we can count "
            "how many people get from upload to download; it is not a cookie and is never linked to your name. "
            "No accounts, no third party analytics, nothing resold.</p><p><a href='/'>back</a></p>")

BEACONS = {"view", "pick", "submit", "done", "fail", "pitch", "return", "sample", "lead"}


@app.post("/e")
async def beacon(request: Request):
    # ponytail: the page reports its own funnel steps; bots rarely run js, so a view here is a person
    body = (await request.body())[:1024]
    try:
        d = json.loads(body or b"{}")
    except ValueError:
        return Response(status_code=204)
    n = str(d.get("n") or "")
    v = str(d.get("v") or "")
    if n not in BEACONS or not re.fullmatch(r"[0-9A-Za-z]{8,40}", v) or is_bot(ua_of(request)):
        return Response(status_code=204)
    extra = {k: str(d[k])[:80] for k in ("src", "why", "status", "cid", "path") if d.get(k)}
    _write(json.dumps({"t": datetime.now(timezone.utc).isoformat(), "ev": n, "v": v,
                       "ua": ua_of(request)[:120], **extra}))
    return Response(status_code=204)


@app.get("/go/{offer}")
def go_checkout(offer: str, request: Request):
    # ponytail: every checkout link goes through here, so a click is counted before polar takes over
    url = {"onebook": ONETIME_URL, "shelf": SHELF_URL}.get(offer)
    if not url:
        raise HTTPException(404, "no such offer")
    if not is_bot(ua_of(request)):
        event("checkout_click", request, offer=offer, why=(request.query_params.get("why") or "")[:20])
    return RedirectResponse(url, status_code=302)


STEPS = [("view", "Visited (js)"), ("pick", "Picked a file"), ("submit", "Pressed convert"),
         ("converted", "Got an EPUB"), ("wall", "Hit a paywall"), ("pitch", "Saw the offer"),
         ("click", "Clicked checkout"), ("paid", "Paid"), ("paid_convert", "Paid book converted")]
WALLS = ("too many pages", "too big", "ocr-wall")
# a wall is a branch off "pressed convert", not a step after "got an epub"
PARENT = {"pick": "view", "submit": "pick", "converted": "submit", "wall": "submit", "pitch": "wall",
          "click": "pitch", "paid": "click", "paid_convert": "paid"}


def funnel_data(lines, days: int = 7) -> dict:
    """People per funnel step, by first-touch source. Joined on the page's random id `v`."""
    since = datetime.now(timezone.utc).timestamp() - days * 86400
    src: dict[str, str] = {}
    steps: dict[str, set] = {}
    paid_cids, returns = set(), {}
    errs: Counter = Counter()
    server = Counter()
    for line in lines:
        try:
            r = json.loads(line)
            t = datetime.fromisoformat(r["t"]).timestamp()
        except (ValueError, KeyError, TypeError):
            continue
        if t < since:
            continue
        v, ev, err = r.get("v") or "", r.get("ev"), r.get("err") or ""
        human = not is_bot(r.get("ua") or "")
        if ev == "paid":
            paid_cids.add(r.get("checkout_id"))
            server["paid"] += 1
            continue
        if ev == "checkout_click" and human:
            server["click"] += 1
        if ev == "paid_convert":
            server["paid_convert"] += 1
        if r.get("visit") and human and not r.get("checkout_id"):
            server["visit"] += 1
        if "ok" in r and not ev and human:
            if r.get("ok"):
                server["converted"] += 1
            else:
                errs[err.split(":")[0] or "?"] += 1
                if err in WALLS:
                    server["wall"] += 1
        if not v:
            continue
        if ev == "view":
            src.setdefault(v, (r.get("src") or "direct")[:40])
        step = {"view": "view", "pick": "pick", "submit": "submit", "pitch": "pitch",
                "checkout_click": "click", "paid_convert": "paid_convert"}.get(ev)
        if not ev and "ok" in r:
            step = "converted" if r.get("ok") else ("wall" if err in WALLS else None)
        if ev == "return" and r.get("cid"):
            returns[v] = r["cid"]
        if step:
            steps.setdefault(step, set()).add(v)
    steps["paid"] = {v for v, c in returns.items() if c in paid_cids} | steps.get("paid_convert", set())
    sources = Counter(src.values())
    rows = []
    for name in ["all"] + [k for k, _ in sources.most_common(12)]:
        who = set(src) if name == "all" else {v for v, sv in src.items() if sv == name}
        rows.append({"source": name, **{k: len(steps.get(k, set()) & who) for k, _ in STEPS}})
    return {"days": days, "rows": rows, "errors": dict(errs.most_common(12)),
            "server": {k: server[k] for k in ("visit", "converted", "wall", "click", "paid", "paid_convert")}}


@app.get("/funnel")
def funnel(request: Request):
    if not FUNNEL_KEY or request.query_params.get("k") != FUNNEL_KEY:
        raise HTTPException(404, "Not Found")
    try:
        days = max(1, min(90, int(request.query_params.get("days") or 7)))
    except ValueError:
        days = 7
    lines = []
    for f in (LOG.with_suffix(".log.1"), LOG):
        try:
            lines += f.read_text().splitlines()
        except OSError:
            pass
    d = funnel_data(lines, days)
    if request.query_params.get("format") == "json":
        return d
    head = "".join(f"<th>{html.escape(lbl)}</th>" for _, lbl in STEPS)
    body = ""
    for r in d["rows"]:
        cells = ""
        for k, _ in STEPS:
            n, up = r[k], r.get(PARENT.get(k, ""), 0)
            # ponytail: the % is against the step it came from, so the worst drop is the smallest number
            pct = f" <i>{round(100 * n / up)}%</i>" if up else ""
            cells += f"<td>{n}{pct}</td>"
        body += f"<tr><th>{html.escape(r['source'])}</th>{cells}</tr>"
    srv = "".join(f"<li>{k}: <b>{v}</b></li>" for k, v in d["server"].items())
    errs = "".join(f"<li>{html.escape(k)}: <b>{v}</b></li>" for k, v in d["errors"].items()) or "<li>none</li>"
    k = html.escape(FUNNEL_KEY)
    nav = " ".join(f'<a href="/funnel?k={k}&days={n}">{n}d</a>' for n in (1, 7, 30, 90))
    return HTMLResponse(f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Funnel - pdf2epub</title>
<style>body{{margin:0;background:#faf7f0;color:#1b1916;font-family:system-ui,sans-serif;line-height:1.5}}
.wrap{{max-width:1100px;margin:0 auto;padding:32px 16px}}h1{{font-size:22px;margin:0 0 6px}}
p,li{{color:#5b564d;font-size:14px}}.scroll{{overflow-x:auto}}table{{border-collapse:collapse;font-size:13px;margin:16px 0}}
th,td{{border:1px solid #e4ded2;padding:6px 9px;text-align:right;white-space:nowrap}}
thead th{{background:#f4f0e7;text-align:center}}tbody th{{text-align:left}}
td i{{color:#a3301f;font-style:normal;font-size:11px}}a{{color:#553bc4;margin-right:6px}}</style></head>
<body><div class="wrap"><h1>Funnel, last {d['days']} days</h1><p>{nav}</p>
<p>People, not hits: each column counts distinct browsers (the page's random id). The red % is the share
that made it from the step before. The smallest red number is where you lose people.</p>
<div class="scroll"><table><thead><tr><th>Source</th>{head}</tr></thead><tbody>{body}</tbody></table></div>
<p><b>Server-side counts</b> (humans by user agent, works without js):</p><ul>{srv}</ul>
<p><b>Failures by reason</b>:</p><ul>{errs}</ul>
<p><a href="/funnel?k={k}&days={d['days']}&format=json">json</a></p></div></body></html>""")


@app.get("/stats")
def stats():
    # ponytail: totals from log file, no DB/dashboard lib
    ok = fail = pages = visits = ocr = scan_fail = emails = 0
    leads = cap_rejects = checkouts = 0
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
            if r.get("ev"):
                continue  # ponytail: funnel steps live in /funnel, they are not visits or conversions
            ua = r.get("ua") or ""
            if r.get("visit"):
                visits += 1
                checkouts += 1 if r.get("checkout_id") else 0  # ponytail: polar lands on /thanks with the id
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
            leads += 1 if c.startswith("lead") else 0
            cap_rejects += 1 if c in ("too many pages", "too big") else 0
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
            "emails_captured": emails, "leads": leads, "cap_rejects": cap_rejects,
            "checkouts": checkouts,
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


SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _span_text(s):
    # ponytail: flattening spans loses the superscript flag, so a footnote marker reads as a
    # normal digit glued to the sentence ("argument.12"). unicode keeps it visibly raised.
    t = s["text"]
    if s["flags"] & 1 and t.strip().isdigit() and len(t.strip()) <= 3:
        return t.translate(SUP)
    return t


FIG_SCALE = 3  # 3x keeps 4pt map labels readable; this book's 23 figures add ~6MB
CAPTION_RE = re.compile(r"^(map|figure|fig\.?|table|plate|chart|diagram)\b", re.I)


def _body_size(doc):
    """Dominant font size of long lines, estimated once for the whole document."""
    sizes = []
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b.get("lines", []):
                txt = "".join(s["text"] for s in line["spans"]).strip()
                if len(txt) >= 40:
                    sizes.append(max(s["size"] for s in line["spans"]))
    return Counter(sizes).most_common(1)[0][0] if sizes else 0


def _page_rect(page, rect):
    """Map a text/drawing rect to the page's rendered orientation."""
    return rect * page.rotation_matrix if page.rotation else rect


def _figure_rect(page, blocks, body):
    """Clip rect for a page that is mostly a figure, else None.

    Maps in this book are vector drawings with the labels as tiny text blocks. The EPUB had no
    images at all, so the map vanished and its labels leaked into the prose. Rendering the
    region keeps the map and the labels in one picture.
    """
    area = page.rect.width * page.rect.height
    rects = []
    for info in page.get_image_info():
        r = pymupdf.Rect(info["bbox"])
        if (r.width * r.height) / area > 0.03:
            rects.append(r)
    drawings = page.get_drawings()
    if len(drawings) >= 15:
        rs = [d["rect"] for d in drawings]
        u = pymupdf.Rect(min(r.x0 for r in rs), min(r.y0 for r in rs),
                         max(r.x1 for r in rs), max(r.y1 for r in rs))
        if (u.width * u.height) / area > 0.10:
            rects.append(u)
    if not rects:
        return None
    u = rects[0]
    for r in rects[1:]:
        u |= r
    # ponytail: a full-page scan (cover, index) already has a text layer; rasterising it would
    # hide the text, so leave those alone.
    if (u.width * u.height) / area > 0.8:
        return None
    # A page of prose with an equation or a rule through it is not a figure. If body-size text
    # sits inside the box, keep the text and skip the picture (math books hit this hard). Short
    # map labels do not count; a paragraph does. The 9pt floor catches 9.5pt exercise text in
    # books whose main body size is 10.5pt.
    min_body = min(body * 0.95, 9.0) if body else 9.0
    body_chars = 0
    for b in blocks:
        if b.get("type") != 0:
            continue
        r = pymupdf.Rect(b["bbox"])
        if not u.contains(pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)):
            continue
        for line in b.get("lines", []):
            spans = line["spans"]
            text = "".join(s["text"] for s in spans).strip()
            if len(text) >= 10 and max(s["size"] for s in spans) >= min_body:
                body_chars += len(text)
    if body_chars >= 80:
        return None
    return u & page.mediabox


def _blocks(doc):
    """Yield (page_no, y0, size, text) per text block, lines joined into one paragraph.

    ponytail: a visual line is not a paragraph. One wrapped paragraph came out as one
    <p> per line, which is exactly the "break paragraphs weird" complaint. PDF blocks
    are the paragraph unit, so join inside the block. Figure pages yield one extra block
    with size -1 and a (PNG bytes, caption) tuple as text.
    """
    body = _body_size(doc)
    for i, page in enumerate(doc):
        raw = page.get_text("dict")["blocks"]
        fig = _figure_rect(page, raw, body)
        fig_page = _page_rect(page, fig) if fig else None
        cap, cap_page = "", None
        if fig:
            # Put a "Map 4.1 ..." caption under its picture. PDF block order is not y-sorted,
            # so without this the caption can land a paragraph after the map. Captions on
            # landscape pages sit beside the figure in PDF space, so compare on the page.
            for cb in raw:
                if cb.get("type") != 0:
                    continue
                cr = pymupdf.Rect(cb["bbox"])
                cr_page = _page_rect(page, cr)
                if not (fig_page.y1 - 2 <= cr_page.y0 <= fig_page.y1 + 35):
                    continue
                lines = ["".join(_span_text(s) for s in line["spans"]).strip()
                         for line in cb.get("lines", [])]
                txt = _join([x for x in lines if x])
                if CAPTION_RE.match(txt):
                    cap, cap_page = txt, cr_page
                    break
        fig_done = False
        for b in raw:
            if fig and not fig_done and b["bbox"][1] > fig.y1:
                pm = page.get_pixmap(matrix=pymupdf.Matrix(FIG_SCALE, FIG_SCALE), clip=fig_page)
                yield i, fig.y0, -1.0, (pm.tobytes("png"), cap)
                fig_done = True
            if fig:
                r = pymupdf.Rect(b["bbox"])
                center = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
                center = center * page.rotation_matrix if page.rotation else center
                if fig_page.contains(center) or (cap_page and cap_page.contains(center)):
                    continue  # labels and caption are baked into the figure or its figcaption
            if b.get("type") != 0:
                continue
            lines, size = [], 0.0
            for line in b.get("lines", []):
                txt = "".join(_span_text(s) for s in line["spans"]).strip()
                if not txt:
                    continue
                lines.append(txt)
                size = max(size, max(s["size"] for s in line["spans"]))
            if not lines:
                continue
            yield i, b["bbox"][1], round(size, 1), _join(lines)
        if fig and not fig_done:
            pm = page.get_pixmap(matrix=pymupdf.Matrix(FIG_SCALE, FIG_SCALE), clip=fig_page)
            yield i, fig.y0, -1.0, (pm.tobytes("png"), cap)

def _structure(blocks, doc):
    """blocks -> chapters: [[(kind, text), ...], ...]. shared by /convert and the landing proof.

    Footnote blocks (smaller type at the bottom of a page, starting with a marker) are moved
    to the end of the chapter they belong to, under a "Notes" block. Kept as ("fn", text).
    """
    long = [sz for _, _, sz, t in blocks if sz > 0 and len(t) > 40]
    body = Counter(long).most_common(1)[0][0] if long else Counter(sz for _, _, sz, _ in blocks).most_common(1)[0][0]
    h1_cut = body * 1.3
    h2_cut = body * 1.12
    # ponytail: small-font blocks at page bottom that open with a note marker. captions and
    # tables rarely start with "12 ", so the false-positive cost is a moved paragraph, not loss.
    fn_cut = body * 0.95
    fn_mark = re.compile(r"^(?:\d{1,3}(?!\d)[.)]?|[a-zA-Z][.)]|\*|∗|†|‡|§|¶)\s*[A-Za-z\"“‘(]")
    # ponytail: a page of nothing but small type is a TOC or an index, not a page with notes
    body_pages = Counter(p for p, _, sz, _ in blocks if sz >= fn_cut)
    # headings set in the body font ("CHAPTER 1" alone on its page) would otherwise split nothing
    head_word = re.compile(r"^(chapter|part|book|prologue|epilogue|introduction|conclusion|"
                           r"bibliography|references|appendix|index)\b[\s\dIVXLC.:-]*$", re.I)
    # ponytail: publisher page furniture changes per page (DOI, download date), so the repeated
    # header/footer counter never catches it; "Downloaded from <url>" is the common watermark.
    # Cambridge puts the "terms of use" line first in the same block, so match it anywhere.
    boiler = re.compile(r"downloaded from\s+https?:/{1,2}|^https?://doi\.org/", re.I)

    # strip repeated header/footer: same text on >50% pages at top/bottom edge
    ph = doc[0].rect.height
    tops = Counter(t for p, y, sz, t in blocks if y < 60)
    bots = Counter(t for p, y, sz, t in blocks if y > ph - 60)
    n = len(doc)
    banned = {t for t, c in list(tops.items()) + list(bots.items()) if c > n * 0.5}

    chapters, cur, cur_notes = [], [], []
    def flush():
        if cur:
            cur.extend(("fn", t) for t in cur_notes)
            chapters.append(cur.copy())
            cur.clear()
        cur_notes.clear()
    for pno, y, sz, t in blocks:
        if sz < 0:
            cur.append(("img", t))
            continue
        if t in banned or boiler.search(t) or re.fullmatch(r"[\d\s.\-–—]+", t):
            continue  # ponytail: page numbers/running heads dropped, no config
        # ponytail: a running head carries its page number, so the text differs on every page
        # and the repeated-header counter misses it; it sits at the top edge in smaller type.
        if y < 60 and sz < fn_cut and len(t) < 120 and re.search(r"\d", t):
            continue
        # shortcut: marker + small font + bottom half is a heuristic; a numbered list set in
        # smaller type at the foot of a page can be moved into Notes. upgrade to a ruled-off
        # / superscript-marker check if that shows up in real books.
        if sz < fn_cut and fn_mark.match(t) and y > doc[pno].rect.height * 0.55 \
           and body_pages[pno] >= 3 and re.search(r"[a-z]{3}", t):
            cur_notes.append(t)
        elif (sz >= h1_cut or head_word.match(t)) and len(t) < 120:
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
async def convert(request: Request, f: UploadFile = File(...), title: str = Form(""), author: str = Form(""),
                  email: str = Form(""), preview: str = Form("")):
    throttle(request)
    ref = ref_of(request)
    key = shelf_key(request)  # ponytail: a paying subscriber gets a bigger ceiling, no account needed
    raw = await f.read()
    kb_in = len(raw) // 1024
    # ponytail: ?paid=CHECKOUT_ID is the $5 one-book, converted on the spot instead of by hand
    cid = (request.query_params.get("paid") or "")[:80]
    digest = hashlib.sha256(raw).hexdigest()[:32]
    book = bool(cid) and onebook_ok(cid, digest)
    if cid and not book:
        log(False, 0, kb_in, 0, "paid-refused", ref, request=request)
        raise HTTPException(402, "this checkout is not confirmed as paid, or it already converted a "
                            f"different book. Reply to the Polar receipt or email {SHELF_MAIL}")
    paid = bool(key or book)
    max_pages = SHELF_MAX_PAGES if paid else MAX_PAGES
    max_mb = SHELF_MAX_MB if paid else MAX_MB
    if len(raw) > max_mb * 1024 * 1024:
        log(False, 0, kb_in, 0, "too big", ref, email.strip()[:120], request=request)
        raise HTTPException(413, f"over {max_mb}MB - one book is $5 (up to 2,000 pages)"
            if not paid else f"over {max_mb}MB, that is the top of the paid tier, email {SHELF_MAIL} and I will do it")
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
    if len(doc) > max_pages:
        n0 = len(doc)
        doc.close()
        log(False, n0, kb_in, 0, "too many pages", ref, email.strip()[:120], request=request)
        raise HTTPException(413, f"over {max_pages} pages ({n0} here) - one book is $5 (up to 2,000 pages)"
            if not paid else f"over {max_pages} pages, that is the top of the paid tier, email {SHELF_MAIL}")

    def done(data: bytes, pages: int, kind: str):
        log(True, pages, kb_in, len(data) // 1024, kind, ref, email.strip()[:120], request=request)
        if book:
            onebook_use(cid, digest)
            event("paid_convert", request, checkout_id=cid, pages=pages)
        return StreamingResponse(BytesIO(data), media_type="application/epub+zip",
            headers={"Content-Disposition": "attachment; filename=book.epub"})

    blocks = list(_blocks(doc))
    npages = len(doc)
    meta = doc.metadata or {}
    # ponytail: most PDFs carry their own /Title and /Author, so the two fields are usually a no-op
    safe_title = (title or (meta.get("title") or "").strip()
                  or (f.filename or "book").rsplit(".", 1)[0])[:120] or "book"
    author = (author or (meta.get("author") or "").strip())[:120]
    if not blocks:
        # scanned PDF: OCR is the only thing that helps before falling back
        cut = preview == "1" and not paid and npages > FREE_OCR_PAGES
        if npages > FREE_OCR_PAGES and not paid and not cut:
            doc.close()
            log(False, npages, kb_in, 0, "ocr-wall", ref, email.strip()[:120], request=request)
            raise HTTPException(402, f"scanned PDF ({npages} here) - free OCR reads the first "
                                f"{FREE_OCR_PAGES} pages, the whole book is $5")
        if cut:
            doc.select(range(FREE_OCR_PAGES))  # ponytail: the free taste of a long scan, then the wall
        if npages <= (PAID_OCR_MAX_PAGES if paid else FREE_OCR_PAGES) or cut:
            pages = ocr_doc(doc, layout=True) or []
            texts = [t for t, _ in pages]
            if texts and sum(len(t) for t in texts) > 200:
                figs = _scan_figures(doc, pages)
                chapters = ocr_chapters(texts, figs)
                if cut:
                    chapters.append([("h1", "The rest of this book"),
                        ("p", f"This is the free preview: the first {FREE_OCR_PAGES} of {npages} pages. "
                              "The whole book is $5 at epub.ftak.net, converted on the spot.")])
                data = build_epub(chapters, safe_title, author[:120])
                doc.close()
                return done(data, len(texts), "ocr-preview" if cut else ("ocr+fig" if figs else "ocr"))
        # ponytail: calibre still last resort (image-only epub beats error)
        doc.close()
        fb = calibre_convert(raw)
        if fb:
            return done(fb, npages, "calibre-fallback")
        big = npages > PAID_OCR_MAX_PAGES
        log(False, npages, kb_in, 0, "scan-over-ocr-cap" if big else "scan-no-text", ref, request=request)
        raise HTTPException(422, f"scanned PDF, {npages} pages, too long to OCR in one go. Email it to "
                            f"{SHELF_MAIL} and I will run it overnight"
            if big else "scanned PDF — OCR found no readable text (photo of handwriting?)")
    chapters = _structure(blocks, doc)

    data = build_epub(chapters, safe_title, author[:120])
    # ponytail: nothing stored, files die with request — matches their privacy pitch for free
    doc.close()
    return done(data, npages, "")

@app.exception_handler(HTTPException)
async def http_err(request: Request, exc: HTTPException):
    if "text/html" in request.headers.get("accept", ""):
        return err_page(str(exc.detail), exc.status_code)
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, port=8000)
