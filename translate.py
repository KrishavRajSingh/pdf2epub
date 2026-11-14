"""Translate a PDF into another language (ftak.net/translate-pdf talks to these routes).

First FREE_PAGES pages are free. The rest needs a paid Polar checkout (TRANSLATE_PRODUCT), which
unlocks up to PAID_PAGES pages of the same uploaded file. Each page goes to the same vision model the
Library pass uses: text pages as text, scanned pages as an image, so scans need no separate OCR step.
Output is a new, readable PDF (one translated page per source page), not the original layout.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import base64
import html
import json
import re
import secrets
import threading
import time
import urllib.request

import pymupdf
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

router = APIRouter()

FREE_PAGES = 20
PAID_PAGES = 300
MAX_MB = 100
KEEP_SECONDS = 24 * 3600  # source PDF stays this long so a buyer can pay and get the rest
THREADS = 6
TRANSLATE_URL = "https://buy.polar.sh/polar_cl_UHTspV0YklFX4viALXZBOoqhzOIDVeOCTCDSu3GQd3r"  # $5, success -> ftak.net/translate-pdf?paid=
TRANSLATE_PRODUCT = "39e5abb6-0f3e-47dd-8a0a-0f4055f29973"
ORIGINS = {"https://ftak.net", "https://www.ftak.net", "http://localhost:3000"}

LANGS = {
    "en": "English", "hi": "Hindi", "es": "Spanish", "pt": "Portuguese", "fr": "French", "de": "German",
    "it": "Italian", "ru": "Russian", "ar": "Arabic", "zh": "Simplified Chinese", "ja": "Japanese",
    "ko": "Korean", "id": "Indonesian", "vi": "Vietnamese", "tr": "Turkish", "bn": "Bengali", "ur": "Urdu",
    "te": "Telugu", "ta": "Tamil", "mr": "Marathi", "fa": "Persian", "pl": "Polish", "nl": "Dutch",
    "uk": "Ukrainian", "th": "Thai", "fil": "Filipino",
}
RTL = {"ar", "ur", "fa"}

_POOL = ThreadPoolExecutor(max_workers=2)


def _core():
    import app  # ponytail: lazy, app.py includes this router at its end
    return app


def _dir() -> Path:
    d = _core().JOB_DIR / "translate"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(jid: str, ext: str) -> Path:
    if not re.fullmatch(r"[0-9A-Za-z_-]{20,40}", jid or ""):
        raise HTTPException(404, "no such job")
    return _dir() / f"{jid}.{ext}"


def _state(jid: str) -> dict:
    try:
        return json.loads(_path(jid, "json").read_text())
    except (OSError, ValueError):
        raise HTTPException(404, "no such job, it may have expired (files are kept 24 hours)")


def _save(jid: str, st: dict):
    p = _path(jid, "json")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(st))
    tmp.replace(p)


def _cors(request: Request, resp):
    origin = request.headers.get("origin", "")
    if origin in ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
    return resp


PROMPT = ("Translate this page of a document into {lang}. Translate everything, including headings, "
          "captions and table text. Keep the meaning exact; do not summarize, skip or add anything. "
          "Keep names, numbers and formulas as they are. Output plain text only: put each heading on its "
          "own line starting with '# ', separate paragraphs with a blank line, write table rows as lines "
          "with ' | ' between cells. If the page has no text, output nothing.")


def _ask(content, lang: str) -> str | None:
    core = _core()
    body = {"model": core.SHARP_MODEL, "temperature": 0, "reasoning": {"enabled": False},
            "messages": [{"role": "user", "content": content}]}
    for _ in range(2):
        try:
            r = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", json.dumps(body).encode(),
                                       {"Authorization": "Bearer " + core.OPENROUTER_KEY,
                                        "Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=180) as resp:
                j = json.load(resp)
            return (j["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:
            print(f"translate: {type(e).__name__}: {str(e)[:120]}", flush=True)
    return None


def page_input(page) -> tuple[str, str]:
    """What the model sees for one page: its text, or a JPEG of it when it is a scan.

    ponytail: pymupdf is not thread-safe, so this runs in one thread; only the model calls are parallel.
    """
    text = page.get_text("text").strip()
    if len(text) >= 80:
        return "text", text[:12000]
    pix = page.get_pixmap(dpi=150)
    if max(pix.width, pix.height) > 2400:
        pix = page.get_pixmap(dpi=int(150 * 2400 / max(pix.width, pix.height)))
    return "image", base64.b64encode(pix.tobytes("jpeg", jpg_quality=80)).decode()


def ask_page(inp: tuple[str, str], lang: str, ask=None) -> str | None:
    ask = ask or _ask
    prompt = PROMPT.format(lang=LANGS[lang])
    kind, data = inp
    if kind == "text":
        return ask(prompt + "\n\nPage text:\n\n" + data, lang)
    return ask([{"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + data}}], lang)


def _page_html(n: int, txt: str | None) -> str:
    parts = [f'<p class="pg">Page {n}</p>']
    if txt is None:
        parts.append('<p class="miss">This page could not be translated. Try again later.</p>')
    for block in re.split(r"\n\s*\n", (txt or "").strip()):
        block = block.strip()
        if not block:
            continue
        if block.startswith("# "):
            parts.append(f"<h2>{html.escape(block[2:].strip())}</h2>")
        else:
            parts.append("<p>" + "<br/>".join(html.escape(x) for x in block.splitlines()) + "</p>")
    return "".join(parts)


CSS = """
body { font-size: 11pt; line-height: 1.5; }
h2 { font-size: 14pt; margin: 10pt 0 4pt 0; }
p { margin: 0 0 7pt 0; }
.pg { font-size: 8pt; color: #888; margin-bottom: 8pt; }
.miss { color: #a00; }
"""


def build_pdf(pages: list[tuple[int, str | None]], lang: str, note: str = "") -> bytes:
    """One translated source page starts a new output page (long ones run on).

    ponytail: css page-break-before makes Story.place loop forever, so each page is its own Story.
    """
    import io
    direction = ' dir="rtl"' if lang in RTL else ""
    blocks = [_page_html(n, txt) for n, txt in pages]
    if note:
        blocks.append(f"<p>{html.escape(note)}</p>")
    buf = io.BytesIO()
    w = pymupdf.DocumentWriter(buf)
    rect = pymupdf.paper_rect("a4")
    where = rect + (54, 54, -54, -54)
    for block in blocks:
        story = pymupdf.Story(html=f"<body{direction}>{block}</body>", user_css=CSS)
        more, guard = 1, 0
        while more and guard < 50:
            dev = w.begin_page(rect)
            more, _ = story.place(where)
            story.draw(dev)
            w.end_page()
            guard += 1
    w.close()
    return buf.getvalue()


def _run(jid: str, first: int, last: int):
    """Translate pages first..last (1-based, inclusive) of the stored PDF, then write the output PDF."""
    st = _state(jid)
    try:
        doc = pymupdf.open(_path(jid, "pdf"))
        nums = list(range(first, last + 1))
        inputs = {n: page_input(doc.load_page(n - 1)) for n in nums}
        doc.close()
        done: dict[int, str | None] = {}
        lock = threading.Lock()

        def one(n):
            res = ask_page(inputs[n], st["lang"])
            with lock:
                done[n] = res
                st["done"] = len(done)
                _save(jid, st)

        with ThreadPoolExecutor(max_workers=THREADS) as ex:
            list(ex.map(one, nums))
        rest = st["pages"] - last
        note = ""
        if rest > 0:
            note = (f"The free translation covers the first {last} of {st['pages']} pages. "
                    f"Translate the other {rest} at ftak.net/translate-pdf")
        out = build_pdf([(n, done.get(n)) for n in nums], st["lang"], note)
        _path(jid, "out.pdf").write_bytes(out)
        failed = sum(1 for n in nums if done.get(n) is None)
        st.update(status="done", translated=last, failed=failed, finished=time.time())
        _save(jid, st)
        _core().event("translate_done", None, job=jid, pages=st["pages"], translated=last, failed=failed,
                      lang=st["lang"], paid=bool(st.get("paid")))
    except Exception as e:
        st.update(status="error", error=f"{type(e).__name__}")
        _save(jid, st)
        _core().event("translate_error", None, job=jid, err=f"{type(e).__name__}: {str(e)[:80]}")


def _sweep():
    now = time.time()
    for p in _dir().glob("*.json"):
        try:
            if now - p.stat().st_mtime > KEEP_SECONDS:
                for q in _dir().glob(p.stem + ".*"):
                    q.unlink(missing_ok=True)
        except OSError:
            pass


@router.options("/translate")
@router.options("/translate/{jid}/full")
def translate_preflight(request: Request, jid: str = ""):
    resp = JSONResponse({})
    resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Max-Age"] = "86400"
    return _cors(request, resp)


@router.post("/translate")
async def translate_start(request: Request, f: UploadFile = File(...), lang: str = Form("en")):
    core = _core()
    core.throttle(request, limit=10, day_limit=40)
    if lang not in LANGS:
        raise HTTPException(400, "pick a language from the list")
    if not core.OPENROUTER_KEY:
        raise HTTPException(503, "translation is offline right now, try again later")
    raw = await f.read()
    if len(raw) > MAX_MB * 1024 * 1024:
        raise HTTPException(413, f"that file is over {MAX_MB} MB")
    try:
        doc = pymupdf.open(stream=raw, filetype="pdf")
        pages = doc.page_count
    except Exception:
        raise HTTPException(400, "that file doesn't open as a PDF")
    if pages < 1:
        raise HTTPException(400, "that PDF has no pages")
    await run_in_threadpool(_sweep)
    jid = secrets.token_urlsafe(18)
    _path(jid, "pdf").write_bytes(raw)
    name = re.sub(r"[^\w .()-]+", "", (f.filename or "document.pdf"))[:80] or "document.pdf"
    st = {"status": "working", "pages": pages, "lang": lang, "name": name, "done": 0,
          "free": min(FREE_PAGES, pages), "started": time.time()}
    _save(jid, st)
    core.event("translate_start", request, job=jid, pages=pages, lang=lang, kb=len(raw) // 1024)
    _POOL.submit(_run, jid, 1, st["free"])
    return _cors(request, JSONResponse({"job": jid, **st}))


@router.get("/translate/{jid}")
def translate_status(jid: str, request: Request):
    st = _state(jid)
    st.pop("paid_cid", None)
    st["checkout"] = f"https://epub.ftak.net/go/translate?why={jid[:20]}" if TRANSLATE_URL and st["pages"] > st["free"] else ""
    st["more_pages"] = max(0, st["pages"] - st.get("translated", st["free"]))
    return _cors(request, JSONResponse(st, headers={"Cache-Control": "no-store"}))


@router.get("/translate/{jid}/pdf")
def translate_file(jid: str):
    st = _state(jid)
    p = _path(jid, "out.pdf")
    if not p.exists():
        raise HTTPException(404, "not ready yet")
    stem = st["name"][:-4] if st["name"].lower().endswith(".pdf") else st["name"]
    out = f"{stem} ({LANGS[st['lang']]}).pdf"
    return FileResponse(p, media_type="application/pdf", filename=out)


@router.post("/translate/{jid}/full")
def translate_full(jid: str, request: Request, checkout: str = Form("")):
    """After payment: translate the rest of the same file, up to PAID_PAGES pages."""
    core = _core()
    st = _state(jid)
    if st.get("paid"):
        return _cors(request, JSONResponse(st))
    if not TRANSLATE_PRODUCT or not core.paid_checkout(checkout, TRANSLATE_PRODUCT):
        raise HTTPException(402, "this checkout is not confirmed as paid yet. Wait a minute and retry, "
                            f"or reply to the Polar receipt")
    used = _dir() / "paid-used.txt"
    try:
        for line in used.read_text().splitlines():
            if line.split()[0] == checkout and line.split()[1] != jid:
                raise HTTPException(402, "this payment already translated a different file")
    except OSError:
        pass
    with used.open("a") as fh:
        fh.write(f"{checkout} {jid}\n")
    last = min(st["pages"], PAID_PAGES)
    st.update(status="working", paid=True, paid_cid=checkout, done=0, translated=0)
    _save(jid, st)
    core.event("translate_paid", request, job=jid, pages=st["pages"])
    _POOL.submit(_run, jid, 1, last)
    return _cors(request, JSONResponse({"job": jid, "status": "working"}))
