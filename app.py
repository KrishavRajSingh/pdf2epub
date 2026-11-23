"""PDF -> EPUB MVP. Free text-only. No auth, no DB, no storage."""
from collections import Counter
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
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
import threading
import time
import traceback
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.parse
import urllib.request
import pymupdf
from ebooklib import epub
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool
try:
    from guides import GUIDES, INDEX_BODY
except Exception:  # ponytail: a missing file must not take the site down
    GUIDES, INDEX_BODY = {}, "<p>Guides are unavailable right now.</p>"
FAQ = {"en": [
    ("Will it work on my Kindle?",
     "Yes. Send the EPUB to your Kindle with Amazon's Send to Kindle (by email, the app or the web page) and it "
     "lands in your library. Kobo, Apple Books and most phone readers open it as it is."),
    ("Is my file kept anywhere?",
     "No. The PDF is never saved, and the finished EPUB is deleted ten minutes after you download it, so a second tap still works (or after an hour if you never do). There is no account and no library on this side."),
    ("My PDF is a scanned book. Does that work?",
     "Yes. Scanned pages are read with OCR, then split into chapters and paragraphs like any other PDF. "
     "Scans up to __FREEOCR__ pages are free. A longer scan is $5 once for the whole book, full refund if you are not happy."),
    ("What happens to footnotes and maps?",
     "Footnotes move to the end of their chapter, under Notes. Maps, figures and pages that are mostly a picture "
     "come through as images."),
    ("Can it convert a book I bought from Kindle or Kobo?",
     "No. Store books are locked with DRM and are not PDFs. It converts PDFs you can open yourself."),
    ("What if my book has more than 150 pages?",
     "Books up to 150 pages convert free. A longer book is $5 once and converts whole, up to 2,000 pages, "
     "with a full refund if you are not happy. "
     "Anything bigger is still $5: email us and we raise the limit for your book."),
    ("What if the paid conversion is not good enough?",
     "Email me within 30 days and I refund the full amount, no questions asked."),
]}
try:
    from i18n import LANGS, FAQS
    FAQ.update(FAQS)
except Exception:  # ponytail: same rule, the english page must survive a missing translation file
    LANGS = {}
import time

app = FastAPI()
MAX_MB = 1000  # ponytail: launched at 50, then 200; 11-08 a 490MB upload was refused 3x, a 1GB test peaks ~5GB of the 8GB box
BIG_MB = 200  # ponytail: files over this convert one at a time across both workers, so two 1GB books cannot OOM the box together
BIG_LOCK = Path(os.environ.get("JOB_DIR", "/tmp/pdf2epub-jobs")).parent / "pdf2epub-big.lock"
MAX_PAGES = 150  # ponytail: 500 let almost every book through, so the $5 offer met ~1 reader a day (11-03)
OCR_MAX_PAGES = 200
# ponytail: OCR is the expensive work and the real pain, so that is where the wall sits. text PDFs
# stay free to 150 pages; a scan is free to 20 pages, then $5 unlocks the whole book right away
FREE_OCR_PAGES = 20
PAID_OCR_MAX_PAGES = 2000  # ponytail: 11-08 raised from 600 (user: run big paid scans as one long job, never refuse). ponytail: OCR runs as a background job now (the page polls), so railway's
# 5-minute idle cut no longer applies. 11-05: a 302-page scan in the request got a 502 and was thrown away
OCR_THREADS = 4  # ponytail: tesseract is a subprocess, so threads run it in parallel; hobby plan has 8 vCPU
FIG_MAX_PX = 2000  # ponytail: long side cap; 3x renders of a full page are ~1850x2400
JOB_DIR = Path(os.environ.get("JOB_DIR", "/tmp/pdf2epub-jobs"))  # ponytail: /tmp is shared by both uvicorn workers
JOB_TTL = 3600  # an unfetched epub is deleted after an hour
JOB_MAX_RUN = 6 * 3600  # ponytail: the longest a job may run (2,000-page OCR); the page polls this long
GOT_GRACE = 600  # ponytail: a re-click or a phone download manager re-fetch within 10 min still gets the file (11-08: 200 then 404 x2)
RESEND_KEY = os.environ.get("RESEND_API_KEY", "")
# ponytail: epub.ftak.net was added in resend on 11-05 (dns on vercel); until resend verifies it, a send
# from it is refused, so fall back to opencorp.live (verified). no code change needed once it verifies
MAIL_FROMS = [x for x in [os.environ.get("MAIL_FROM", ""), "pdf2epub <books@epub.ftak.net>",
                          "pdf2epub <books@opencorp.live>"] if x]
MAIL_AFTER = 90  # ponytail: mail the link only if the epub is still unfetched this long after it is done
_JOB_POOL = ThreadPoolExecutor(max_workers=2)  # per uvicorn worker, so 4 books at once on the box
OCR_MAX_PX = 3400  # long side; A4 at 200dpi is 2339
OCR_DPI = 200  # ponytail: 300 was 2x the cpu for no readable gain on print; trial credit is scarce
SCAN_FIG_DPI = 150  # ponytail: full-page scan at 200dpi is 4k pixels; 150 keeps maps readable and epub smaller
SCAN_MAX_PAGES = 60  # ponytail: 60 phone photos per batch keeps OCR under a couple of minutes  # ponytail: sync OCR ~2-5 req-min this size, queue (RQ) when bigger scans show up
SHELF_URL = "https://buy.polar.sh/polar_cl_1jZLYsY7lODWs2QOnhNALMww3O7if69LL4nRQ1JiNmJ"  # pdf2epub org, verified 200
ONETIME_URL = "https://buy.polar.sh/polar_cl_ORKV379p0AcaC2enSVTF9bL0IhujaIgYdrajV0D3mtc"  # $5 one book: unlocks the converter for one book up to 2,000 pages
SHELF_MAIL = "krishavrajsingh@gmail.com"
SHELF_PRODUCT = "8c3386ae-0aea-4dd2-87bc-7735b8af795a"
# ponytail: the first shelf buyer did ~20 books in one night and turned renewal off the same day.
# a shelf is a one-time job, so the same limits are sold once for 30 days too
BATCH_URL = "https://buy.polar.sh/polar_cl_DIV8bQHOvUqSGLvGPOceLOSWaSGxXDe0iQPm54gL2Cl"
BATCH_PRODUCT = "4c35ff8c-8fc9-451b-9861-815c5448e733"
BATCH_DAYS = 30
# ponytail (11-14): a reader with 1,000+ Telugu scans asked how to pay for the rest of his library.
# Tesseract misreads faded old print (bake-off 0.87); Gemini Flash-Lite reads it at 0.97 for ~$0.0015 a
# page, so the Library pass re-reads only the pages Tesseract was unsure of, up to a page budget per key
LIBRARY_URL = "https://buy.polar.sh/polar_cl_q3VCOcOJTr6AVmzofpCh8HNq5HTx2BM7a0nBU1y7hT8"  # $25 once, 90 days
LIBRARY_PRODUCT = "a90d0daf-0e76-4129-a94b-7f6eaa71a021"
LIBRARY_DAYS = 90
LIBRARY_SHARP = 8000  # pages; ~$12 of model spend at most on a $25 pass
SHARP_CONF = 90  # ponytail: same cut as scripts/manual_convert.py --gdrive: novels average 86-93, magazines 53-75
SHARP_MODEL = os.environ.get("SHARP_MODEL", "google/gemini-3.1-flash-lite")
SHARP_THREADS = 6
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
# Google Drive OCR, free: an OCR-only Google account's refresh token (drive.file scope) on a desktop OAuth client
DRIVE_CLIENT_ID = os.environ.get("DRIVE_CLIENT_ID", "")
DRIVE_CLIENT_SECRET = os.environ.get("DRIVE_CLIENT_SECRET", "")
DRIVE_REFRESH = os.environ.get("DRIVE_REFRESH_TOKEN", "")
DRIVE_THREADS = 6
ONEBOOK_PRODUCT = "c9dd91ab-92b9-4d82-a79d-191bd965cd86"
# ponytail: 11-10 price test. Half the books over the free cap are 165-412 pages and the rival's
# smallest pack is $3.75, so books up to 400 pages are offered at $3 instead of $5.
SHORT_URL = "https://buy.polar.sh/polar_cl_0xs3znrEUDiRWhJrHmHtJhaL6utEFjmHy1nDI2jpW3C"
SHORT_PRODUCT = "154810a2-37a4-4b8a-bc21-cb68fbd67ad8"
SHORT_MAX_PAGES = 400
POLAR_TOKEN = os.environ.get("POLAR_TOKEN", "")  # ponytail: read-only OAT, only orders:read is needed
POLAR_ORDERS = "https://api.polar.sh/v1/orders/"
# ponytail: a paying subscriber gets a key that lifts the per-file ceiling. no accounts, no db:
# the key is a secret string we mail them, they put it in the url as ?k=KEY
SHELF_KEYS = Path(os.environ.get("LOG_DIR", ".")) / "shelf-keys.txt"  # one key per line
PAID = Path(os.environ.get("LOG_DIR", ".")) / "paid-checkouts.txt"  # verified ids, so refresh is free
USED = Path(os.environ.get("LOG_DIR", ".")) / "used-checkouts.txt"  # one-book id + file hash, one book per payment
FREEBOOK = Path(os.environ.get("LOG_DIR", ".")) / "freebook.txt"  # token email ip date [digest], one free whole book per email
# ponytail (11-16): Cloudflare Web Analytics, same visitor counter as QRigin/DOMolition; the funnel stays on our log
CF_BEACON = '<script defer src="https://static.cloudflareinsights.com/beacon.min.js" data-cf-beacon=\'{"token": "33b7cc180a8c4904b7cef84cbfbbc46b"}\'></script>'  # ggignore: public beacon id, served in every page's HTML, not a credential
FUNNEL_KEY = os.environ.get("FUNNEL_KEY", "")  # ponytail: /funnel shows money numbers, so it needs ?k=
SHELF_MAX_PAGES = 2000  # ponytail: the free tier stops at 150, a preview of most books
SHELF_MAX_MB = 1000
LOG = Path(os.environ.get("LOG_DIR", ".")) / "conversions.log"  # ponytail: on Railway set LOG_DIR=/data + volume, else dies with container
_HITS: dict[str, list[float]] = {}  # ponytail: in-mem throttle, redis when paid


def _epub_disp(fn: str) -> str:
    """Content-Disposition naming the EPUB after the uploaded PDF.

    ponytail: browsers let this header beat the page's a.download, so "book.epub" here renamed every
    folder conversion to the same name (ysvsr 11-14). filename* carries Telugu and other non-ASCII names.
    """
    base = re.sub(r"[\x00-\x1f\x7f/\\\"]", "", (fn or "").rsplit("/", 1)[-1])
    base = re.sub(r"\.pdf$", "", base, flags=re.I).strip()[:150] or "book"
    name = base + ".epub"
    ascii_ = re.sub(r"[^\x20-\x7e]", "_", name)
    return f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{urllib.parse.quote(name)}"


def shelf_key(request: Request) -> str:
    """Return the subscriber's key if the request carries a valid one.

    ponytail: the key rides in the url, so check the query string and the referer, because the
    form posts to /convert + location.search and some clients drop the query on the post.
    """
    k = (request.query_params.get("k") or request.headers.get("x-k") or "").strip()
    if not k:
        m = re.search(r"[?&]k=([0-9A-Za-z_-]{6,64})", (request.headers.get("referer") or "")[:120])
        k = m.group(1) if m else ""
    if not k:
        return ""
    try:
        lines = SHELF_KEYS.read_text().splitlines()
    except OSError:
        return ""
    today = datetime.now(timezone.utc).date().isoformat()
    want = _key_fold(k)
    for ln in lines:
        # ponytail: "CHECKOUT KEY" for shelf, "CHECKOUT KEY until=YYYY-MM-DD" for a batch pass
        parts = ln.split()
        if len(parts) >= 2 and _key_fold(parts[1]) == want:
            k = parts[1]  # ponytail: the stored spelling, so the Library budget is counted on one key
            until = next((p[6:] for p in parts[2:] if p.startswith("until=")), "")
            if until:
                return k if today <= until else ""
            return k if shelf_active(parts[0]) else ""
    return ""


_KEY_FOLD = str.maketrans("1IO", "ll0")


def _key_fold(k: str) -> str:
    """A key with its lookalike letters folded: 1/I/l all read as l, O as 0.

    ponytail: a Batch buyer typed his key into a second Mac twice (11-11, 11-19) with a 1 for
    the l, and every book there fell back to the free preview while the page said "Paid key active".
    keys are 20 random chars, so folding a few lookalikes cannot make two buyers' keys collide.
    """
    return k.translate(_KEY_FOLD)


SHELF_GRACE_DAYS = 34  # ponytail: a month plus 3 days, so a renewal that lands a day late never locks anyone out
_SHELF_CACHE: dict[str, tuple[float, bool]] = {}


def shelf_active(cid: str) -> bool:
    """A Shelf key works while the buyer's latest paid Shelf order is under 34 days old.

    ponytail: every monthly renewal is a new polar order, so the read-only orders token is enough
    (it cannot read /subscriptions). A cancel stops the renewals, so the key ends a month after the
    last payment. Fail open: a polar outage or a hand-made key ("manual ...") never locks a buyer out.
    """
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", cid) or not POLAR_TOKEN:
        return True
    hit = _SHELF_CACHE.get(cid)
    if hit and time.time() - hit[0] < 6 * 3600:
        return hit[1]
    def get(q):
        req = urllib.request.Request(POLAR_ORDERS + q, headers={"Authorization": "Bearer " + POLAR_TOKEN,
                                                                "User-Agent": "pdf2epub/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return (json.load(r) or {}).get("items") or []
    try:
        first = get("?limit=1&checkout_id=" + cid)
        if not first:
            return True
        cust = first[0].get("customer_id") or ""
        orders = [o for o in get(f"?limit=10&customer_id={cust}&product_id={SHELF_PRODUCT}&sorting=-created_at")
                  if o.get("status") == "paid"]
        last = max(datetime.fromisoformat(o["created_at"].replace("Z", "+00:00")) for o in orders) if orders else None
    except Exception:
        return True
    ok = bool(last) and datetime.now(timezone.utc) - last < timedelta(days=SHELF_GRACE_DAYS)
    _SHELF_CACHE[cid] = (time.time(), ok)
    return ok


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
    # ponytail: cloudflare bans python-urllib's default UA (error 1010), so name ourselves
    req = urllib.request.Request(POLAR_ORDERS + "?limit=1&checkout_id=" + cid,
                                 headers={"Authorization": "Bearer " + POLAR_TOKEN,
                                          "User-Agent": "pdf2epub/1.0"})
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


def onebook_pages(cid: str) -> int:
    """Page limit a paid one-book checkout buys: 2,000 for the $5 book, 400 for the $3 one, 0 unpaid."""
    if paid_checkout(cid, ONEBOOK_PRODUCT):
        return SHELF_MAX_PAGES
    return SHORT_MAX_PAGES if paid_checkout(cid, SHORT_PRODUCT) else 0


def onebook_ok(cid: str, digest: str) -> int:
    """A paid one-book checkout converts one file (re-running that file stays free). Returns its
    page limit, 0 when the checkout is unpaid or already used on a different file."""
    try:
        for line in USED.read_text().splitlines():
            parts = line.split()
            if parts and parts[0] == cid and parts[1:2] != [digest]:
                return 0
    except OSError:
        pass
    return onebook_pages(cid)


def onebook_use(cid: str, digest: str):
    # ponytail: the file hash, never the file, so "nothing stored" stays true
    try:
        with USED.open("a") as fh:
            fh.write(f"{cid} {digest}\n")
    except OSError:
        pass


def _freebook_rows() -> list[list[str]]:
    try:
        return [l.split() for l in FREEBOOK.read_text().splitlines() if l.strip()]
    except OSError:
        return []


def freebook_ok(token: str, digest: str) -> bool:
    """A free-book token converts one whole book (re-running that same file stays free)."""
    rows = _freebook_rows()
    if not token or not any(r[0] == token for r in rows):
        return False
    used = [r for r in rows if r[0] == "used" and r[1:2] == [token]]
    return not used or any(r[2:3] == [digest] for r in used)


def freebook_use(token: str, digest: str):
    try:
        with FREEBOOK.open("a") as fh:
            fh.write(f"used {token} {digest}\n")
    except OSError:
        pass


def issue_key(checkout_id: str, days: int = 0, sharp: int = 0) -> str:
    """Mint a key for a paid checkout, once per checkout id.

    ponytail: no accounts, no db, no polar api call. the key is a random string in a file on the
    volume, and the checkout id is remembered so a refresh of the page does not mint a second one.
    """
    try:
        done = SHELF_KEYS.read_text()
    except OSError:
        done = ""
    m = re.search(rf"^{re.escape(checkout_id)}\s+(\S+)", done, re.M)
    if m:
        return m.group(1)
    key = secrets.token_urlsafe(15)
    try:
        with SHELF_KEYS.open("a") as fh:
            until = (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat() if days else ""
            fh.write(f"{checkout_id} {key}" + (f" until={until}" if until else "")
                     + (f" sharp={sharp}" if sharp else "") + "\n")
    except OSError:
        pass
    print(json.dumps({"t": datetime.now(timezone.utc).isoformat(), "key_issued": checkout_id,
                      "ua": ""}), flush=True)
    # ponytail: only a fresh key is mailed, so a refresh of /thanks never sends a second mail.
    # a thread, so a slow polar or resend never holds up the buyer's success page
    threading.Thread(target=_mail_key, args=(checkout_id, key, days, sharp), daemon=True).start()
    return key


SHARP_USED = Path(os.environ.get("LOG_DIR", ".")) / "sharp-used.txt"  # "KEY PAGES" per book
_SHARP_LOCK = threading.Lock()


def sharp_left(key: str) -> int:
    """Pages of AI re-reading this key still has (0 for keys without the Library pass)."""
    if not key:
        return 0
    try:
        lines = SHELF_KEYS.read_text().splitlines()
    except OSError:
        return 0
    total = 0
    for ln in lines:
        parts = ln.split()
        if len(parts) >= 2 and parts[1] == key:
            total = next((int(p[6:]) for p in parts[2:] if re.fullmatch(r"sharp=\d+", p)), 0)
    if not total:
        return 0
    try:
        used = sum(int(b) for a, b in (ln.split() for ln in SHARP_USED.read_text().splitlines() if ln.strip())
                   if a == key)
    except (OSError, ValueError):
        used = 0
    return max(0, total - used)


LANG_NAMES = {"te": "Telugu", "hi": "Hindi", "en": "English", "pt": "Portuguese", "es": "Spanish"}


def _sharp_page(img: bytes, lang: str) -> str | None:
    """One page image read by the vision model; None on any failure (the Tesseract text stays)."""
    import base64
    prompt = (f"Transcribe every piece of text on this scanned page exactly as printed, mostly "
              f"{LANG_NAMES.get(lang, 'English')}. Follow reading order: columns left to right, each column "
              "top to bottom. Keep spelling exactly as printed; do not correct, modernize, translate, "
              "summarize or add anything. Write [?] for a word you cannot read. Ignore handwriting, pen marks, "
              "underlining and margin notes. Write each paragraph as one line, with a blank line between "
              "paragraphs. If the page has no printed text, output nothing. Output only the text.")
    body = {"model": SHARP_MODEL, "temperature": 0, "reasoning": {"enabled": False},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(img).decode()}}]}]}
    for _ in range(2):
        try:
            r = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", json.dumps(body).encode(),
                                       {"Authorization": "Bearer " + OPENROUTER_KEY, "Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=180) as resp:
                j = json.load(resp)
            text = (j["choices"][0]["message"]["content"] or "").strip()
            if text:
                return text
        except Exception as e:
            print(f"sharp: {type(e).__name__}: {str(e)[:120]}", flush=True)
    return None


def sharp_pages(doc, layout: list, confs: dict, lang: str, key: str, read=None, img=None) -> int:
    """Swap Tesseract text for the vision model's on the pages Tesseract was unsure of, in place.

    ponytail: same page pick as scripts/manual_convert.py --gdrive, capped by the key's page budget.
    Returns the number of pages swapped (only those count against the budget)."""
    read = read or _sharp_page
    if not (OPENROUTER_KEY or read is not _sharp_page):
        return 0
    left = sharp_left(key)
    todo = [i for i, (t, _) in enumerate(layout) if confs.get(i, 100) < SHARP_CONF
            and (len(t.split()) >= 20 or confs.get(i) == 0)][:left]
    if not todo:
        return 0
    imgs = {}
    for i in todo:  # pymupdf is not thread-safe: render here, call the model in threads
        p = doc[i]
        dpi = min(200, int(2000 * 72 / max(p.rect.width, p.rect.height)))
        imgs[i] = img(i) if img else p.get_pixmap(dpi=dpi).tobytes("jpg", jpg_quality=88)
    with ThreadPoolExecutor(SHARP_THREADS) as ex:
        got = dict(zip(todo, ex.map(lambda i: read(imgs.pop(i), lang), todo)))
    ok = 0
    for i, text in got.items():
        n = len(layout[i][0].split())
        if text and len(text.split()) >= (0.5 * n if n >= 20 else 40):
            layout[i] = (text, layout[i][1])
            ok += 1
    if ok:
        with _SHARP_LOCK, SHARP_USED.open("a") as fh:
            fh.write(f"{key} {ok}\n")
    print(json.dumps({"t": datetime.now(timezone.utc).isoformat(), "sharp": ok, "asked": len(todo),
                      "pages": len(layout)}), flush=True)
    return ok


_DRIVE_TOKEN = {"v": "", "exp": 0.0}
_DRIVE_LOCK = threading.Lock()


def _drive_token() -> str:
    with _DRIVE_LOCK:
        if time.time() < _DRIVE_TOKEN["exp"]:
            return _DRIVE_TOKEN["v"]
        body = urllib.parse.urlencode({"client_id": DRIVE_CLIENT_ID, "client_secret": DRIVE_CLIENT_SECRET,
                                       "refresh_token": DRIVE_REFRESH, "grant_type": "refresh_token"}).encode()
        with urllib.request.urlopen("https://oauth2.googleapis.com/token", body, timeout=30) as r:
            j = json.load(r)
        _DRIVE_TOKEN.update(v=j["access_token"], exp=time.time() + int(j.get("expires_in", 3600)) - 300)
        return _DRIVE_TOKEN["v"]


def _drive_clean(text: str) -> str:
    # ponytail: the export starts with a BOM and a "____" rule where the image sat; each line is a paragraph
    lines = [l.strip().lstrip("﻿") for l in text.splitlines()]
    return "\n\n".join(l for l in lines if l and not re.fullmatch(r"_+", l))


def _drive_page(img: bytes, lang: str) -> str | None:
    """One page image read by Google Drive's OCR (upload as a Google Doc, export text, delete);
    None on any failure. Same calls as scripts/gdrive_ocr.py, over plain HTTP."""
    api = "https://www.googleapis.com"
    for _ in range(2):
        fid = None
        try:
            tok = _drive_token()
            b = "pdf2epub" + uuid.uuid4().hex
            meta = json.dumps({"name": "pdf2epub-ocr-" + b[-10:], "mimeType": "application/vnd.google-apps.document"})
            body = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
                    f"--{b}\r\nContent-Type: image/jpeg\r\n\r\n").encode() + img + f"\r\n--{b}--\r\n".encode()
            req = urllib.request.Request(f"{api}/upload/drive/v3/files?uploadType=multipart&fields=id&ocrLanguage={lang}",
                                         body, {"Authorization": "Bearer " + tok,
                                                "Content-Type": f"multipart/related; boundary={b}"})
            with urllib.request.urlopen(req, timeout=120) as r:
                fid = json.load(r)["id"]
            req = urllib.request.Request(f"{api}/drive/v3/files/{fid}/export?mimeType=text/plain",
                                         headers={"Authorization": "Bearer " + tok})
            with urllib.request.urlopen(req, timeout=120) as r:
                return _drive_clean(r.read().decode("utf-8", "replace"))
        except Exception as e:
            print(f"drive: {type(e).__name__}: {str(e)[:120]}", flush=True)
        finally:
            if fid:
                try:
                    urllib.request.urlopen(urllib.request.Request(f"{api}/drive/v3/files/{fid}", method="DELETE",
                                           headers={"Authorization": "Bearer " + _drive_token()}), timeout=30)
                except Exception:
                    pass
    return None


def reread_pages(doc, layout: list, confs: dict, lang: str, key: str, drive=None, read=None) -> int:
    """Paid keys: unsure OCR pages go to Drive's free OCR first, then pages Drive missed go to the
    AI re-read while the key has Library pages left. In place; returns pages swapped.

    ponytail: ysvsr's 1,000 AI pages ran out after 8 books and the rest came out as raw Tesseract
    (11-18). Drive scored 0.95 vs Tesseract 0.87 on hard Telugu pages and costs nothing."""
    drive = drive or (_drive_page if DRIVE_REFRESH else None)
    done = 0
    if drive:
        todo = [i for i, (t, _) in enumerate(layout) if confs.get(i, 100) < SHARP_CONF
                and (len(t.split()) >= 20 or confs.get(i) == 0)]
        imgs = {}
        for i in todo:  # pymupdf is not thread-safe: render here, upload in threads
            p = doc[i]
            dpi = min(200, int(2000 * 72 / max(p.rect.width, p.rect.height)))
            imgs[i] = p.get_pixmap(dpi=dpi).tobytes("jpg", jpg_quality=88)
        with ThreadPoolExecutor(DRIVE_THREADS) as ex:
            got = dict(zip(todo, ex.map(lambda i: drive(imgs.pop(i), lang), todo)))
        confs = dict(confs)
        for i, text in got.items():
            n = len(layout[i][0].split())
            if text and len(text.split()) >= (0.5 * n if n >= 20 else 40):
                layout[i] = (text, layout[i][1])
                confs[i] = 100.0  # read: the AI pass skips it
                done += 1
        print(json.dumps({"t": datetime.now(timezone.utc).isoformat(), "drive": done, "asked": len(todo),
                          "pages": len(layout)}), flush=True)
    if sharp_left(key):
        done += sharp_pages(doc, layout, confs, lang, key, read)
    return done


def _strip_pen(page) -> tuple[bytes, bool]:
    """(grey JPEG of the page with blue and red pen ink painted over in the paper's tone, any ink found).

    ponytail: a library copy with blue-ink margin notes and underlining (davehasl19, The Feasting
    Dead, 11-21): every OCR read the handwriting as words ("strained O* on", "aXe") and the chapter
    numerals as junk. Only coloured pixels go, so black print under an underline stays readable."""
    from PIL import Image, ImageChops, ImageStat
    # ponytail: 2200px on the long side; at 2000 Drive dropped an underlined line and a drop cap (11-21).
    # Growing the ink mask by a pixel cost more print than the faint ink edges it caught.
    dpi = min(220, int(2200 * 72 / max(page.rect.width, page.rect.height)))
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    r, g, b = im.split()
    blue = ImageChops.subtract(b, r).point(lambda v: 255 if v > 18 else 0)
    red = ImageChops.subtract(r, g).point(lambda v: 255 if v > 45 else 0)
    mask = ImageChops.lighter(blue, red)
    grey = im.convert("L")
    inked = ImageStat.Stat(mask).mean[0] / 255 > 0.002
    if inked:
        grey.paste(int(ImageStat.Stat(grey).median[0]), mask=mask)
    buf = BytesIO()
    grey.save(buf, "JPEG", quality=88)
    return buf.getvalue(), inked


def layer_scan_pages(doc, lang: str, key: str = "", drive=None, read=None) -> list | None:
    """Pages of a scan that carries someone else's OCR layer, read again: pen ink removed, Google
    Drive's OCR first, then for paid keys the AI re-read on inked pages and failed reads.
    [(text, 1.0), ...], or None when Drive is not set up or failed on most pages (the caller then
    keeps the old text layer).

    ponytail: Internet Archive and similar scans come with an old OCR layer that the text path
    copied as-is; three books from one r/ebooks reader (11-18..11-21) all had misreads the printed
    page does not ("imtil", "PON SO LORN" for "A Story", handwriting as words). Drive read each one
    clean and costs nothing, so it runs for every reader; only the AI pass is paid."""
    drive = drive or (_drive_page if DRIVE_REFRESH else None)
    if not drive or not len(doc):
        return None
    pages, confs, inked, failed, drove = [], {}, set(), 0, set()
    step = DRIVE_THREADS * 8  # ponytail: a 2,000-page paid book would hold ~400MB of page images at once
    for a in range(0, len(doc), step):
        part = list(range(a, min(a + step, len(doc))))
        win = {}
        for i in part:  # pymupdf is not thread-safe: render here, upload in threads
            try:
                win[i] = _strip_pen(doc[i])
            except Exception:
                win[i] = (doc[i].get_pixmap(dpi=150).tobytes("jpg", jpg_quality=88), False)
        with ThreadPoolExecutor(DRIVE_THREADS) as ex:
            got = list(ex.map(lambda i: drive(win[i][0], lang), part))
        for i, text in zip(part, got):
            if IA_NOTICE.search(doc[i].get_text()):
                text = ""  # the archive's own "Digitized by" page, not the book
            if text is None:
                failed += 1
            elif text:
                drove.add(i)
            pages.append((doc[i].get_text() if text is None else text, 1.0))
            confs[i] = 0.0 if (text is None or win[i][1]) else 100.0
            if win[i][1]:
                inked.add(i)
    if failed > len(doc) / 2:
        return None
    for i in sorted(drove):  # pages Drive read; a failed page keeps the old layer's text as it is
            try:
                pages[i] = (_put_caps(pages[i][0], _cap_rows(doc[i])), pages[i][1])
            except Exception:
                pass  # ponytail: a page whose layer can't be read keeps Drive's text as it is
    sharp = 0
    if key and sharp_left(key) and any(c < SHARP_CONF for c in confs.values()):
        sharp = sharp_pages(doc, pages, confs, lang, key, read, img=lambda i: _strip_pen(doc[i])[0])
    print(json.dumps({"t": datetime.now(timezone.utc).isoformat(), "layer_scan": len(doc), "drive_failed": failed,
                      "inked": len(inked), "sharp": sharp}), flush=True)
    return pages


def _put_caps(text: str, caps: list) -> str:
    """Drive's page text with the drop caps the picture shows put back. ponytail: Drive loses a
    two-line drop cap like the old layer does ("ere's a quick start", Ageless Spine 11-22). The
    layer says which line it starts; the same words starting a line in Drive's text, still
    lowercase, get the letter. Drive's line that already has it ("Here's") does not match."""
    flat = text.replace("\u2019", "'").replace("\u2018", "'")
    for _, row, cap in caps:
        words = row.replace("\u2019", "'").replace("\u2018", "'").split()[:4]
        if len(words) < 2:
            continue
        m = re.search(r"(?:^|\n)[ \t]*(" + r"\s+".join(map(re.escape, words)) + ")", flat)
        if m and flat[m.start(1)].islower():
            k = m.start(1)
            text, flat = text[:k] + cap + text[k:], flat[:k] + cap + flat[k:]
    return text


def _order_email(checkout_id: str) -> str:
    """The email the buyer paid with, from the polar order (the checkout email is the identity)."""
    if not POLAR_TOKEN:
        return ""
    req = urllib.request.Request(POLAR_ORDERS + "?limit=1&checkout_id=" + checkout_id,
                                 headers={"Authorization": "Bearer " + POLAR_TOKEN,
                                          "User-Agent": "pdf2epub/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            items = (json.load(r) or {}).get("items") or []
    except Exception:
        return ""
    return ((items[0].get("customer") or {}).get("email") or "") if items else ""


def _mail_key(checkout_id: str, key: str, days: int = 0, sharp: int = 0):
    """Mail a fresh Shelf or Batch key to the buyer, so losing the tab or the browser never loses it."""
    to = _order_email(checkout_id)
    if not (RESEND_KEY and re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}", to)):
        event("key_mail_failed", None, checkout=checkout_id[:8], err="no resend key or no email")
        return
    name = "Library pass" if sharp else ("Batch pass" if days else "Shelf")
    plan = f"{name} ({days} days, it does not renew)" if days else "Shelf"
    extra = (f"Scans get the sharper AI reading on the pages regular OCR finds hard to read, for up to "
             f"{sharp:,} pages.\n\n") if sharp else ""
    body = (f"Thanks for buying pdf2epub {plan}. Your key:\n\n{key}\n\n" + extra +
            f"Open this link to convert with the paid limits (books up to 2,000 pages, 1GB, scans included):\n\n"
            f"https://epub.ftak.net/?k={key}\n\n"
            "No account, no password. The browser you open it in remembers the key. "
            "Keep this email: on a new device, open the link again.\n\n"
            "A book that comes out wrong? Reply to this email with the title and I will look at it.\n\n"
            "Krishav, pdf2epub")
    ok, err = _send_mail(to, f"Your pdf2epub {name} key", body)
    if ok:
        event("key_mailed", None, checkout=checkout_id[:8], sender=ok)
    else:
        event("key_mail_failed", None, checkout=checkout_id[:8], err=err)


def _send_mail(to: str, subject: str, body: str) -> tuple[str, str]:
    """Send one plain-text mail through resend. Returns (sender domain, "") or ("", error)."""
    err = ""
    for sender in MAIL_FROMS:
        req = urllib.request.Request("https://api.resend.com/emails", method="POST",
            data=json.dumps({"from": sender, "to": [to], "reply_to": SHELF_MAIL,
                             "subject": subject[:120], "text": body}).encode(),
            headers={"Authorization": "Bearer " + RESEND_KEY, "Content-Type": "application/json",
                     "User-Agent": "pdf2epub/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=10):
                return sender.split("@")[-1][:-1], ""
        except urllib.error.HTTPError as e:
            err = f"{e.code} {sender}"
            if e.code not in (403, 422):
                break  # ponytail: only an unverified sender is worth retrying with the next one
        except Exception as e:
            err = str(e)[:80]
            break
    return "", err

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


def crash_reason(e: BaseException) -> str:
    """'crash KeyError in _structure:1234: 'x'' - type, the deepest app.py frame, the message."""
    where = ""
    for fr in traceback.extract_tb(e.__traceback__):
        if fr.filename.endswith("app.py"):
            where = f" in {fr.name}:{fr.lineno}"
    return f"crash {type(e).__name__}{where}: {str(e)[:40]}"[:80]


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
        "<b>A whole shelf:</b> <b>Shelf</b> is $10/month, no monthly limit, any number of books "
        "up to 2,000 pages each: <a href='/go/shelf?why=errpage'>subscribe</a>, or "
        "<a href='/go/batch?why=errpage'>$10 once for 30 days</a>. "
        "Not happy with the result? Full refund within 30 days.</p>"
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
        pix = page.get_pixmap(dpi=_ocr_dpi(page))
    except Exception:
        return "", 0.0
    return _tess(pix.tobytes("png"), pix.width, pix.height)


# Tesseract script name (OSD) -> traineddata to OCR with, and the EPUB language code for it.
# ponytail: Telugu added 11-10 (reddit user, two Telugu novels came out as Latin junk), Hindi
# with it. Add a script here plus its tesseract-ocr-<lang> package in the Dockerfile when asked.
# Latin is split by latin_lang() into the languages the site has pages in (en, pt, es).
OCR_SCRIPTS = {"Telugu": ("tel", "te"), "Devanagari": ("hin", "hi")}
LATIN_LANGS = {"en": "eng", "pt": "por", "es": "spa"}
# words only one of the three languages uses, accents stripped (English OCR drops them)
_STOP = {
    "en": set("the and of to was he that it with his is for you i".split()),
    "pt": set("nao com do da dos das ele ela voce em na um ao muito isso ja entao".split()),
    "es": set("el los las y del con pero muy es su lo ella esta eso ya entonces".split()),
}


def latin_lang(text: str) -> str:
    """"en", "pt" or "es" for Latin-script text, by words only that language uses; English if unsure."""
    plain = unicodedata.normalize("NFKD", text.lower())
    words = re.findall(r"[a-z]+", "".join(c for c in plain if not unicodedata.combining(c)))
    score = {k: sum(w in v for w in words) for k, v in _STOP.items()}
    best = max(score, key=score.get)
    rest = max(v for k, v in score.items() if k != best)
    return best if score[best] >= 5 and score[best] >= 1.5 * rest else "en"


def text_lang(text: str) -> str:
    """EPUB language of a text layer: the Indian script if most letters are one, else latin_lang."""
    counts = Counter("te" if "\u0c00" <= c <= "\u0c7f" else "hi" if "\u0900" <= c <= "\u097f" else "latin"
                     for c in text if c.isalpha())
    top = counts.most_common(1)
    return top[0][0] if top and top[0][0] != "latin" and top[0][1] > 0.5 * sum(counts.values()) \
        else latin_lang(text)
_TESS_LANGS: set | None = None


def _tess_langs() -> set:
    global _TESS_LANGS
    if _TESS_LANGS is None:
        try:
            r = subprocess.run(["tesseract", "--list-langs"], capture_output=True, timeout=20)
            _TESS_LANGS = set(r.stdout.decode().split()[1:]) if r.returncode == 0 else set()
        except Exception:
            _TESS_LANGS = set()
    return _TESS_LANGS


def ocr_lang(doc) -> tuple[str, str]:
    """(tesseract lang, epub lang) for this book: read one page with English and with each
    Indian-script model, keep the one Tesseract is most sure of.

    ponytail: every scan was read with "-l eng" until 11-10, so a Telugu book came out as
    "SAOES aP HISPen Brow...". Script detection (OSD) then called a Telugu scan Bengali,
    Devanagari or nothing (11-10 library sample); mean word confidence was 90 for tel vs 27 for eng."""
    if not len(doc) or not shutil.which("tesseract"):
        return "eng", "en"
    # ponytail: up to 3 pages that have words; one sample page in a magazine was a picture,
    # both models scored 0 and the Telugu magazine was read as English (Cinema Rangam, 11-10)
    n = len(doc)
    score, eng_text, used = Counter(), "", 0
    models = ["eng"] + [t for t, _ in OCR_SCRIPTS.values() if t in _tess_langs()]
    for i in sorted({n // 2, n // 3, (2 * n) // 3, n // 4, (3 * n) // 4, n // 5}, key=lambda k: abs(k - n // 2)):
        if used >= 3:
            break
        try:
            png = doc[i].get_pixmap(dpi=_ocr_dpi(doc[i])).tobytes("png")
        except Exception:
            continue
        runs = {m: _tess(png, 1, 1, m, conf=True) for m in models}
        if max(len(r[0].split()) for r in runs.values()) < 20:
            continue  # a picture or a blank page
        used += 1
        eng_text += runs["eng"][0] + "\n"
        for m, r in runs.items():
            score[m] += r[2]
    if not used:
        return "eng", "en"
    best, best_conf = "eng", score["eng"]
    for m in models[1:]:
        if score[m] > best_conf + 10 * used:
            best, best_conf = m, score[m]
    if best != "eng":
        return best, next(code for t, code in OCR_SCRIPTS.values() if t == best)
    # Latin: pick en/pt/es by its words. ponytail: English OCR on Portuguese drops every ã and ç
    code = latin_lang(eng_text)
    tess = LATIN_LANGS[code]
    return (tess, code) if tess in _tess_langs() else ("eng", "en")


def _tess(png: bytes, page_w: int, page_h: int, lang: str = "eng", conf: bool = False):
    """Tesseract on one rendered page. Thread-safe: no pymupdf objects in here.
    Returns (text, ink coverage); with conf=True (text, coverage, mean word confidence,
    picture boxes), the boxes as page fractions (x0, y0, x1, y1)."""
    fail = ("", 0.0, 0.0, []) if conf else ("", 0.0)
    # ponytail: one OpenMP thread per tesseract; pages already run OCR_THREADS at a time, and the
    # oversubscribed box hit the 60s timeout and dropped whole pages without a word (11-11, 38 Kathalu
    # lost 15k of 50k words). A timeout now gets one long retry instead of an empty page.
    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    r = None
    for limit in (90, 300):
        try:
            r = subprocess.run(["tesseract", "stdin", "stdout", "-l", lang, "tsv"],
                input=png, capture_output=True, timeout=limit, env=env)
            break
        except subprocess.TimeoutExpired:
            print(f"ocr: tesseract timeout {limit}s ({lang})", flush=True)
        except Exception:
            return fail
    if r is None:
        return fail
    if r.returncode != 0:
        return fail
    lines = {}
    ink = 0
    confs = []
    blocks, worded, wboxes = {}, set(), []
    # ponytail: QUOTE_NONE. A word starting with " opened a csv quoted field and swallowed the next
    # rows, so "5 1 2 1 5 4 402 452 90 61 95.07" leaked into the book (Telugu novel, reddit 11-10)
    for row in csv.reader(r.stdout.decode("utf-8", "replace").splitlines(), delimiter="\t",
                          quoting=csv.QUOTE_NONE):
        if len(row) >= 10 and row[0] == "2":
            try:
                blocks[row[2]] = tuple(int(x) for x in row[6:10])
            except ValueError:
                pass
        if len(row) < 12 or row[0] != "5" or not row[11].strip():
            continue
        worded.add(row[2])
        try:
            left, top, width, height = int(row[6]), int(row[7]), int(row[8]), int(row[9])
        except ValueError:
            continue
        lines.setdefault((row[2], row[3], row[4]), []).append((left, row[11].strip()))
        wboxes.append((left, top, left + width, top + height))
        ink += width * height
        try:
            confs.append(float(row[10]))
        except ValueError:
            pass
    # ponytail: group printed lines into tesseract's paragraphs (block, par). Keyed by line, every
    # printed line became its own <p> from 10-23 to 11-05: the "one line per printed line" we sell against.
    paras = {}
    for k, v in sorted(lines.items(), key=lambda kv: tuple(int(x) for x in kv[0])):
        paras.setdefault(k[:2], []).append(" ".join(t for _, t in sorted(v)))
    cov = ink / (page_w * page_h) if page_w and page_h else 0.0
    text = "\n\n".join("\n".join(p) for p in paras.values())
    if conf:
        # ponytail: Tesseract's layout pass marks illustrations as blocks with no words in them.
        # Magazine pictures (Chandamama, 11-10) were dropped; these boxes get cropped as figures
        pics = []
        if page_w > 1 and page_h > 1:
            for b, (x, y, w, h) in blocks.items():
                if b not in worded and w * h >= 0.04 * page_w * page_h and w >= 0.15 * page_w and h >= 0.08 * page_h \
                        and not _covers_text(x, y, x + w, y + h, wboxes):
                    pics.append((x / page_w, y / page_h, (x + w) / page_w, (y + h) / page_h))
        return text, cov, (sum(confs) / len(confs) if confs else 0.0), pics
    return text, cov

def _covers_text(x0, y0, x1, y1, wboxes) -> bool:
    """A word-free block that still has read words inside it is text, not a picture: the spine
    shadow of a book scanned open, two pages a shot, made Tesseract call the column next to it a
    picture, and the novel got 60 crops of its own text (Rudranetra, 38 Kathalu, 11-11)."""
    inside = ink = 0
    for a, b, c, d in wboxes:
        if a >= x0 - 2 and b >= y0 - 2 and c <= x1 + 2 and d <= y1 + 2:
            inside += 1
            ink += (c - a) * (d - b)
    return inside >= 8 or ink >= 0.05 * (x1 - x0) * (y1 - y0)


def _blurred(png: bytes):
    try:
        from PIL import Image, ImageFilter
        im = Image.open(BytesIO(png)).filter(ImageFilter.GaussianBlur(1.2))
        out = BytesIO()
        im.save(out, "PNG")
        return out.getvalue()
    except Exception:
        return None


def _english_paras(native: str, mixed: str) -> str:
    """Swap in the lang+eng reading of only the paragraphs that it reads as English.

    ponytail: a Telugu novel quoting a letter in English (AgniPravesam p.32, ysvsr 11-18) came out
    "0% (౧౭ ౧౭౫౧, 2౧ 260౮2006"; English read the whole page worse, so nothing was swapped. Same
    layout pass, so the paragraphs line up; if they don't, keep the native text."""
    a, b = native.split("\n\n"), mixed.split("\n\n")
    if len(a) != len(b):
        return native
    out = []
    for x, y in zip(a, b):
        letters = [ch for ch in y if ch.isalpha()]
        toks = re.findall(r"[a-z]+", y.lower())
        junk = len(re.findall("[०-९౦-౯0-9]", x)) >= 3
        eng = (len(toks) >= 5 and sum(ch.isascii() for ch in letters) >= 0.8 * len(letters)
               and sum(t in _ANY_STOP for t in toks) >= 0.1 * len(toks))
        out.append(y if junk and eng else x)
    return "\n\n".join(out)


def _halves(png: bytes):
    """Left and right halves of a page image, as PNGs; None on any failure."""
    try:
        from PIL import Image
        im = Image.open(BytesIO(png))
        w, h = im.size
        out = []
        for box in ((0, 0, w // 2, h), (w // 2, 0, w, h)):
            b = BytesIO()
            im.crop(box).save(b, "PNG")
            out.append(b.getvalue())
        return out
    except Exception:
        return None


def _ocr_dpi(page):
    """OCR_DPI, lowered for pages printed huge: a 300dpi scan saved at 72dpi is a 33-inch page,
    and 200dpi of that is a 6700px image where Tesseract finds a sixth of the words (11-11)."""
    side = max(page.rect.width, page.rect.height) or 842
    return max(36, min(OCR_DPI, int(OCR_MAX_PX * 72 / side)))


_VATTU = re.compile(r"[(|]((?:[\u0c15-\u0c39]\u0c4d)*[\u0c15-\u0c39])")


def _fix_vattu(text: str) -> str:
    """Old Telugu typefaces print the ra-vattu (్ర) as a hook before the letter and Tesseract reads
    it as "(" or "|": "(పాణి" for ప్రాణి, "(ప్రజలు", "విశ్వామి(త్రుడు". 4,102 in one Ramayana (11-11).
    A bracket with a ")" close by is a real one and stays."""
    toks = text.split(" ")
    for k, t in enumerate(toks):
        if ("(" in t or "|" in t) and not any(")" in x for x in toks[k:k + 5]):
            toks[k] = _VATTU.sub(lambda m: m.group(1) if "\u0c4d\u0c30" in m.group(1) or
                                 t[m.end():m.end() + 2] == "\u0c4d\u0c30" else m.group(1) + "\u0c4d\u0c30", t)
    return " ".join(toks)


def _tess_mixed(png: bytes, page_w: int, page_h: int, lang: str = "eng"):
    """_tess, and for an Indian-language book a second pass with English on pages where the
    first came out as native digits: a cover or blurb page printed in English read with the
    Telugu model alone gives "111౮1 & 4018010" (11-10). Only those pages pay for the second pass;
    tel+eng on every page garbled some Telugu words."""
    text, cov, c, pics = _tess(png, page_w, page_h, lang, conf=True)
    if page_w > 1.1 * page_h and (not text.strip() or c < 70):
        # ponytail: a book scanned open, two pages a shot. Tesseract's layout pass said "Empty page!!"
        # on whole spreads and they were dropped (AgniPravesam: 4 of 133, ysvsr 11-18); each half reads
        halves = _halves(png)
        if halves:
            rs = [_tess_mixed(h, page_w // 2, page_h, lang) for h in halves]
            n = [len(r[0].split()) for r in rs]
            hc = sum(r[3] * k for r, k in zip(rs, n)) / sum(n) if sum(n) else 0.0
            if sum(n) and (not text.strip() or hc > c):
                hp = [(x0 / 2 + s, y0, x1 / 2 + s, y1) for r, s in zip(rs, (0.0, 0.5)) for x0, y0, x1, y1 in r[2]]
                return "\n\n".join(r[0] for r in rs if r[0].strip()), (rs[0][1] + rs[1][1]) / 2, hp, hc
    if any((x1 - x0) * (y1 - y0) >= 0.4 for x0, y0, x1, y1 in pics):
        # ponytail: paper texture and halftone on a tinted magazine page made Tesseract read three
        # text columns as one picture (Vijayachitra 1986: 64 words of 600, 11-11); a light blur gives 501
        soft = _blurred(png)
        if soft:
            t2, cov2, c2, pics2 = _tess(soft, page_w, page_h, lang, conf=True)
            if len(t2.split()) > len(text.split()):
                text, cov, c, pics = t2, cov2, c2, pics2
                png = soft
    if "eng" not in lang and len(re.findall("[\u0966-\u096f\u0c66-\u0c6f]", text)) >= 3:
        # ponytail: only when English reads the page better. An old magazine typeface also makes
        # native-digit junk, and there lang+eng sprinkled "SHY", "OSH" through the Telugu (11-10)
        if _tess(png, page_w, page_h, "eng", conf=True)[2] > c:
            text, cov = _tess(png, page_w, page_h, lang + "+eng")
        else:
            text = _english_paras(text, _tess(png, page_w, page_h, lang + "+eng")[0])
    if "tel" in lang:
        text = "\n".join(_fix_vattu(l) for l in text.split("\n"))
    return text, cov, pics, c


def _done(w):
    return w if isinstance(w, tuple) else (w.result() if w else ("", 0.0, [], 0.0))


def _clean_layer(page):
    """(text, 1.0) when a page in an OCR'd book is real text, not a picture, with a clean
    layer: a Telugu novel in an old font (11-10) still has its copyright page in plain English,
    which the Telugu model turned into "111౮1 & 4018010". None means OCR the page."""
    try:
        text = page.get_text().strip()
        if len(text) < 40 or _junk_share(text) >= 0.1:
            return None
        # ponytail: Latin-script pages only (the English copyright page). A Unicode Telugu layer
        # can be broken (vowel signs out of order), which is why the book is being OCR'd (11-10)
        letters = [c for c in text if c.isalpha()]
        if not letters or sum(c.isascii() for c in letters) < 0.9 * len(letters) or _mixed_share(text) > 0.15:
            return None
        toks = re.findall(r"[a-z]{2,}", text.lower())
        if len(toks) >= 30 and sum(t in _ANY_STOP for t in toks) < 0.03 * len(toks):
            return None  # Latin letters but no language: font codes
        area = abs(page.rect) or 1
        if sum(abs(pymupdf.Rect(im["bbox"]) & page.rect) for im in page.get_image_info()) / area > 0.5:
            return None
        if any(LEGACY_FONTS.search(f[3]) for f in page.get_fonts()):
            return None
        blocks = [b[4].strip() for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]
        return "\n\n".join(blocks), 1.0
    except Exception:
        return None


def ocr_doc(doc, layout: bool = False, lang: str | None = None, pics: dict | None = None,
            confs: dict | None = None) -> list | None:
    # ponytail: 200dpi render + tesseract CLI, same subprocess pattern as calibre; swap engine if quality complaints
    if not shutil.which("tesseract"):
        return None
    lang = lang or ocr_lang(doc)[0]
    # ponytail: pymupdf is not thread-safe, so pages render one by one here and only tesseract runs
    # in parallel. a small window keeps at most a few rendered pages in memory at once
    out, window = [], []
    with ThreadPoolExecutor(OCR_THREADS) as ex:
        for page in doc:
            layer = _clean_layer(page)
            if layer:
                window.append(layer)
                continue
            try:
                pix = page.get_pixmap(dpi=_ocr_dpi(page))
                window.append(ex.submit(_tess_mixed, pix.tobytes("png"), pix.width, pix.height, lang))
            except Exception:
                window.append(None)
            if len(window) >= OCR_THREADS * 2:
                out.extend(_done(w) for w in window)
                window = []
        out.extend(_done(w) for w in window)
    if pics is not None:  # {page index: [picture boxes as page fractions]}
        pics.update({i: r[2] for i, r in enumerate(out) if len(r) > 2 and r[2]})
    if confs is not None:  # {page index: mean word confidence}; a clean text layer counts as 100
        confs.update({i: (r[3] if len(r) > 3 else 100.0) for i, r in enumerate(out)})
    out = [(r[0], r[1]) for r in out]
    return out if layout else [t for t, _ in out]

def _fig_bytes(pm) -> bytes:
    """A figure as JPEG or PNG, whichever is clearly smaller.

    ponytail: photos come out ~7x smaller as JPEG (a 113MB photo book made a 486MB epub as PNG);
    maps and line art stay PNG, where it is smaller and the labels stay sharp. No classifier.
    """
    try:
        if pm.alpha:
            pm = pymupdf.Pixmap(pm, 0)
        side = max(pm.width, pm.height)
        if side > FIG_MAX_PX:
            k = FIG_MAX_PX / side
            pm = pymupdf.Pixmap(pm, int(pm.width * k), int(pm.height * k), None)
        png = pm.tobytes("png")
        if pm.n not in (1, 3):
            return png
        jpg = pm.tobytes("jpg", jpg_quality=82)
        return jpg if len(jpg) < len(png) * 0.7 else png
    except Exception:
        return pm.tobytes("png")


def _inked(pm) -> bool:
    """A crop with something on it, not a blank margin or a faint stain."""
    try:
        g = pymupdf.Pixmap(pymupdf.csGRAY, pm) if pm.n > 1 else pm
        s = g.samples
        return sum(1 for b in s[::7] if b < 200) > 0.08 * (len(s) / 7)
    except Exception:
        return False


def _scan_figures(doc, pages, pics: dict | None = None):
    """Pictures from scan pages: low-ink pages (maps, plates, tables) whole, so OCR does not turn
    them into prose, and illustration boxes Tesseract found on text pages, cropped (magazines).
    Values are bytes for one picture or a list for several."""
    figs = {}
    for i, boxes in (pics or {}).items():
        if i >= len(doc):
            continue
        r, crops = doc[i].rect, []
        for x0, y0, x1, y1 in boxes:
            if (x1 - x0) * (y1 - y0) >= 0.85:  # the whole page is a picture
                crops = [doc[i].get_pixmap(dpi=SCAN_FIG_DPI)]
                break
            clip = pymupdf.Rect(r.x0 + x0 * r.width, r.y0 + y0 * r.height, r.x0 + x1 * r.width, r.y0 + y1 * r.height)
            pm = doc[i].get_pixmap(dpi=SCAN_FIG_DPI, clip=clip)
            if _inked(pm):
                crops.append(pm)
        if crops:
            figs[i] = [_fig_bytes(pm) for pm in crops]
    for i, (text, cov) in enumerate(pages):
        if i in figs:
            continue
        clean = re.sub(r"\s+", " ", text).strip()
        if len(clean) < 3 or cov >= 0.12:
            continue
        if re.match(r"^(chapter|part|prologue|epilogue|book)\b", clean, re.I):
            continue  # keep sparse chapter openers as text so the TOC still gets them
        # A map can OCR into one huge garbage line; very low ink still means picture.
        if len(clean) >= 1800 and cov >= 0.03:
            continue
        if _wordy(text) and len(clean.split()) >= 30:
            continue  # ponytail: a short chapter-end or poem page is text; whole-page copies filled
            # Telugu memoirs with pictures of their own pages (Brahmanandam 87 of 195, 11-11)
        figs[i] = _fig_bytes(doc[i].get_pixmap(dpi=SCAN_FIG_DPI))
    return figs

def scan_cover(doc, texts: list, figs: dict | None = None) -> bytes | None:
    """The first page of a scan as the EPUB cover, its OCR text dropped (texts/figs edited in place).

    ponytail: a cover is lettering over a picture; OCR read the picture as words, so the book opened
    on "Unpayable dence, the the once deve political me ral" (Jon, 11-21). Kept as text when the
    page holds real prose (a scan that starts mid-book)."""
    if not texts or len(doc) < 20 or any(len(p.split()) >= 40 for p in _page_paras(texts[0])):
        return None  # ponytail: a one-page form or a short scan is all content, no cover
    texts[0] = ""
    if figs is not None:
        figs.pop(0, None)
    try:
        return _jpeg(doc[0].get_pixmap(dpi=SCAN_FIG_DPI))
    except Exception:
        return None


def _jpeg(pm) -> bytes:
    if pm.n - pm.alpha != 3:
        pm = pymupdf.Pixmap(pymupdf.csRGB, pm)
    return pm.tobytes("jpg", jpg_quality=85)


def _wordy(text: str) -> bool:
    """OCR text that reads as words, not map-label junk. A low-ink page (a one-page form, a short
    last page) is kept as a picture and its text too; reddit 11-06 got a picture and no words."""
    toks = text.split()
    # any script, CAPS too; vowel signs (Telugu, Hindi) are marks, not letters, and ZWNJ joins them
    words = [t for t in toks if len(w := t.strip("()[].,:;!?\"'/-")) >= 2
             and all(c.isalpha() or unicodedata.category(c) in ("Mn", "Mc") or c == "\u200c" for c in w)]
    return len(words) >= 5 and len(words) >= 0.6 * len(toks)


HEAD_WORD = re.compile(r"^(chapter|part|prologue|epilogue|book)\b", re.I)


def _page_paras(txt: str) -> list[str]:
    return [" ".join(l.strip() for l in para.splitlines() if l.strip())
            for para in re.split(r"\n\s*\n", txt) if para.strip()]


FOLIO = re.compile(r"[\dIVXLCivxlc]{1,4}")


def _edges(paras: list[str]) -> list[int]:
    """Indexes of the paragraphs a running head can be: first and last, and the one past a bare
    page number. ponytail: Drive OCR gives "8" and "JOHN METCALFE" as two paragraphs (11-21), so
    the head sat second and became a chapter on every left page."""
    if not paras:
        return []
    k = {0, len(paras) - 1}
    if len(paras) > 2 and (FOLIO.fullmatch(paras[0]) or FOLIO.fullmatch(paras[1])):
        k.add(1)
    if len(paras) > 2 and (FOLIO.fullmatch(paras[-1]) or FOLIO.fullmatch(paras[-2])):
        k.add(len(paras) - 2)
    return sorted(k)


def _under_folio(paras: list[str], keys: set) -> int:
    """Index of a "CHAPTER 1" running head under the page number at the top of the page, else -1."""
    for j in (1, 2):
        if j < len(paras) and all(FOLIO.fullmatch(p) for p in paras[:j]) and len(paras[j]) <= 50 \
                and (m := HEAD_WORD.match(paras[j])) and m.group(1).lower() in keys:
            return j
    return -1


def _chapter_heads(pages: list[str]) -> set:
    """Head words ("chapter") whose line sits right under the page number on 3+ pages: there a
    "CHAPTER 2" under a page number is the running head, whatever its number.

    ponytail: _running_heads skips lines that start with "chapter" so real openers stay, but a
    book whose left-page head is "22 / CHAPTER 1" then began a chapter on every left page, ~150
    "CHAPTER 1" entries (Jon, Unpayable Debt, 11-21). A real opener has no page number above it."""
    seen = Counter()
    for txt in pages:
        paras = _drop_caps(_page_paras(txt))[:3]
        for j in (1, 2):
            if j < len(paras) and all(FOLIO.fullmatch(p) for p in paras[:j]) \
                    and HEAD_WORD.match(paras[j]) and len(paras[j]) <= 50:
                seen[HEAD_WORD.match(paras[j]).group(1).lower()] += 1
                break
    return {k for k, c in seen.items() if c >= 3}


def _same_title(para: str, title: str) -> bool:
    """A top line that repeats the chapter already open ("CHAPTER 1" under 'CHAPTER 1 "Not even by
    the law here"', "BIBLIOGRAPHY" on every page of the bibliography) is its running head.

    ponytail: back matter runs 3-10 pages, too few for _running_heads' 1-in-10 count, so every page
    of an index became an INDEX chapter (Jon, Unpayable Debt, 11-21). One stray leading letter is
    allowed: Drive read a mark beside the head as "GCHAPTER 1". Two chapters in a row never share
    a title, so the check needs no count."""
    a, b = _squash(para), _squash(title)
    if len(a) < 5 or not b:
        return False
    return b.startswith(a) or b.startswith(a[1:]) and len(a) > 6


CONTENTS_HEAD = re.compile(r"(table of )?contents", re.I)


def _front(pages: list) -> int:
    """How many opening pages can hold the printed contents page. ponytail: 1/5 of the book alone
    was 4 pages of a 20-page free preview, and Unpayable Debt's contents sit on page 7 (11-22)."""
    return max(15, len(pages) // 5)


LEADER = re.compile(r"\s*\.{2,}.*$")  # "Chapter Two - Design for Life............ 15"


def _contents_pages(pages: list[str]) -> set:
    """Indexes of the printed contents pages in the front of the book. ponytail: Drive OCR put
    "CONTENTS" fifth on Ageless Spine's page, under four dotted entries, and its second page has no
    heading at all, so every dotted entry became a chapter (11-22). A page with the heading anywhere
    near the top counts; the page after one counts when its lines are mostly dot-leader entries."""
    got = set()
    for i, txt in enumerate(pages[: _front(pages)]):
        paras = _page_paras(txt)
        if any(CONTENTS_HEAD.fullmatch(p.strip()) for p in paras[:8]):
            got.add(i)
        elif i - 1 in got and paras:
            dotted = sum(bool(LEADER.search(p)) and len(p) <= 120 for p in paras)
            if dotted >= 4 and dotted * 3 >= len(paras):
                got.add(i)
    return got


def _contents_keys(pages: list[str]) -> set:
    """Entries of the printed contents page ("Future Perfect", 'CHAPTER 1 "Not even..."', "INDEX"),
    squashed to letters and digits; empty when the book has none or it lists under 3 entries."""
    got = []
    for i in sorted(_contents_pages(pages)):
        got += [_squash(LEADER.sub("", p)) for p in _page_paras(pages[i])
                if any(c.isalpha() for c in p) and len(p) <= 120 and not CONTENTS_HEAD.fullmatch(p.strip())]
    return {k for k in got if len(k) >= 3} if len(got) >= 3 else set()


def _squash(t: str) -> str:
    return re.sub(r"[\W_]", "", t.lower())


def _in_contents(para: str, keys: set) -> bool:
    """The line is a contents entry, or its "CHAPTER 1" start (the title sits on the next line)."""
    k = _squash(para)
    if len(k) < 3:
        return False
    if k in keys or bool(HEAD_WORD.match(para)) and any(c.startswith(k) for c in keys):
        return True
    # ponytail: Ageless Spine's contents page spells "Acknowlegements" and "Forward" while the
    # pages say ACKNOWLEDGMENTS and FOREWORD (11-22); a near spelling of a whole entry counts
    return len(k) >= 6 and any(abs(len(c) - len(k)) <= 3 and SequenceMatcher(None, c, k).ratio() >= 0.8
                               for c in keys)


def _running_heads(pages: list[str]) -> set:
    """Keys of short first/last paragraphs that repeat across pages: "మాయ 77", "24 AUTHOR NAME".

    ponytail: the text path drops running headers by position; OCR text had none of that, so a
    Telugu novel (11-10) kept "title + page number" as a paragraph on every page. Digits are
    stripped before comparing, so the page number does not make each one unique."""
    seen = Counter()
    for txt in pages:
        paras = _page_paras(txt)
        for para in {paras[j] for j in _edges(paras)}:
            if len(para) <= 50 and not HEAD_WORD.match(para):
                for k in {_head_key(para), _head_first(para)}:
                    if len(k) >= 3:
                        seen[k] += 1
    return {k for k, c in seen.items() if c >= max(3, len(pages) // 10)}


def _words(para: str) -> list:
    return [k for t in para.split() if len(k := _head_key(t)) >= 3]


def _head_words(pages: list[str]) -> set:
    """Words that keep coming back in short first/last paragraphs: the title and author in a
    running head, however OCR mangled the page number and brackets around them ("[38 కాలిబర్‌ C48)")."""
    seen = Counter()
    for txt in pages:
        paras = _page_paras(txt)
        for para in {paras[j] for j in _edges(paras)}:
            if len(para) <= 50 and not HEAD_WORD.match(para):
                seen.update(set(_words(para)))
    return {w for w, c in seen.items() if c >= max(3, len(pages) // 10)}


def _mostly_head_words(para: str, head_words: set) -> bool:
    w = _words(para)
    return bool(w) and sum(x in head_words for x in w) * 2 >= len(w)


def _head_first(para: str) -> str:
    """Title word of a short "title + page number" line: OCR misreads the number as letters
    ("మాయ డే", "మాయ ర్‌1"), so the whole line no longer repeats but its first word does."""
    toks = para.split()
    return "#" + _head_key(toks[0]) if 2 <= len(toks) <= 3 and len(para) <= 25 and len(toks[-1]) <= 4 else ""


def _head_key(text: str) -> str:
    # letters and vowel signs only: \W would strip Telugu/Hindi vowel signs and shrink the key
    return "".join(c for c in text if c.isalpha() or unicodedata.category(c) in ("Mn", "Mc")).lower()


def _ornament(text: str) -> bool:
    """A dingbat scene break OCR'd as letters: "రె రె ర రె ర", "ష్‌ ష్‌ ష్‌"."""
    toks = text.split()  # ponytail: no Latin letters, so "No, no, no." dialogue never matches
    return (len(toks) >= 4 and all(len(t) <= 3 for t in toks) and len(set(toks)) <= 3
            and not any(c.isascii() and c.isalpha() for c in text))


NUMBERED = re.compile(r"^([0-9]{1,3})[.)]\s+\S.{0,38}(?<![0-9])$")  # "23. ఆ కిటికీ"; "01. గతం 18" is a contents line


def _caps_head(text: str) -> bool:
    """ALL CAPS short line = heading, but only for Latin text: Telugu has no case, so one stray
    Latin capital in it made the whole line "upper" and a heading (11-10)."""
    letters = [c for c in text if c.isalpha()]
    latin = [c for c in letters if c.isascii()]
    # ponytail: one letter is a drop cap ("T" of "THEY") or a stray quote ("I'"), not a heading,
    # unless it is the chapter numeral itself (11-21). Two-letter caps words were never headings either
    if len(letters) < 3 and not re.fullmatch(r"[IVXLC]{1,4}\.?", text):
        return False  # also "TA", "TH": faint pen-ink edges left after the ink is painted out
    return bool(letters) and len(latin) >= 0.8 * len(letters) and text.isupper() and len(text) <= 60


def _drop_caps(paras: list[str]) -> list[str]:
    """Glue a drop cap OCR'd as its own paragraph back onto its word: "T" + "HEY were" -> "THEY were".

    ponytail: Drive OCR puts the big first letter of a chapter on its own line, before or after the
    chapter numeral ("Q", "III", "UESTION and answer", 11-21). A lone I, V or X at the top of the page
    followed by a word is the numeral, not a drop cap ("I", "UR boy")."""
    out, i = [], 0
    while i < len(paras):
        p = paras[i]
        if re.fullmatch(r"[A-Z]", p) and not (p in "IVX" and not out and i + 1 < len(paras)
                                               and re.match(r"[A-Z]{2,}\b", paras[i + 1])):
            for j in (i + 1, i + 2):  # (a lone I/V/X first on the page before a CAPS word: the numeral)
                if j < len(paras) and re.match(r"[A-Z]{2,}\b", paras[j]) and not FOLIO.fullmatch(paras[j]):
                    paras = paras[:j] + [p + paras[j]] + paras[j + 1:]
                    p = None
                    break
            if p is None:
                i += 1
                continue
        out.append(p)
        i += 1
    return out


def _story_numbers(pages: list[str]) -> bool:
    """A story collection: 3+ short paragraphs like "23. ఆ కిటికీ" with different numbers."""
    nums = {m.group(1) for txt in pages for para in _page_paras(txt) if (m := NUMBERED.match(para))}
    return len(nums) >= 3


def ocr_chapters(pages: list[str], figures: dict | None = None, toc: dict | None = None):
    """Tesseract text -> same (kind, text) rows the text path emits. toc: {page index: title}
    from the PDF's own bookmarks, used as chapter breaks when present."""
    # ponytail: paragraphs = tesseract blank-line blocks, headings by keyword/CAPS — no layout model needed for prose
    chapters, cur = [], []
    heads = _running_heads(pages)
    chapter_heads = _chapter_heads(pages)
    contents = _contents_keys(pages)
    contents_pages = _contents_pages(pages)
    head_words = _head_words(pages)
    stories = _story_numbers(pages)
    letters = [c for c in "".join(pages[:: max(1, len(pages) // 40)]) if c.isalpha()]
    # ponytail: in a Telugu magazine the CAPS lines are English ads ("MITSUBISHI PAPER MILLS LTD.", 11-11)
    latin = not letters or sum(c.isascii() for c in letters) >= 0.5 * len(letters)

    def flush():
        if cur:
            chapters.append(cur.copy())
            cur.clear()

    head_page, title_done, open_title = -1, False, ""
    for i, txt in enumerate(pages):
        if toc and i in toc:
            flush()
            cur.append(("h1", toc[i]))
            open_title = toc[i]
        if figures and i in figures:
            for fig in (figures[i] if isinstance(figures[i], list) else [figures[i]]):
                cur.append(("img", (fig, "")))
            if not _wordy(txt):
                continue  # ponytail: a map or plate OCRs to junk, the picture alone carries it
        paras = _drop_caps(_page_paras(txt))
        if i in contents_pages:
            continue  # ponytail: the printed contents page; its "CHAPTER 1 ..." lines became chapters (11-21)
        # ponytail: a title page is short lines only and its title is the running head's words, so
        # "THE FEASTING" was dropped as a head and "DEAD" stood alone (11-21). Heads sit over text.
        edges = _edges(paras) if any(len(p.split()) >= 8 for p in paras) else []
        placed = 0  # text paragraphs already taken from this page
        is_head = lambda q: len(q) <= 50 and (_head_key(q) in heads or _head_first(q) in heads
                                              or _mostly_head_words(q, head_words))
        top = _under_folio(paras, chapter_heads)
        for j, para in enumerate(paras):
            if j <= top:
                continue  # page number(s) + a "CHAPTER 1" running head
            if (head_page == i and len(cur) == 1 and cur[0][0] == "h1" and len(para) <= 80
                    and re.fullmatch(r"(chapter|part|book)\s+[\w.]{1,8}", cur[0][1], re.I)
                    and any(c.isalpha() for c in para) and not HEAD_WORD.match(para)):
                # ponytail: "CHAPTER 1" + its title below: one contents entry. Before the running-head
                # drops: the title is also the right-page head and was dropped here (11-21)
                cur[0] = ("h1", cur[0][1] + " " + para)
                open_title = cur[0][1]
                continue
            # a contents entry that opens a new section is never its own running head
            entry = bool(contents) and len(para) <= 120 and _in_contents(para, contents) \
                and not _same_title(para, open_title) and all(len(q) <= 50 for q in paras[:j])
            if j in edges and FOLIO.fullmatch(para) and any(
                    0 <= k < len(paras) and is_head(paras[k]) for k in (j - 1, j + 1)):
                continue  # the page number beside the running head; "11" reads as "II" and was a chapter
            if (j in edges and len(para) <= 50 and not entry
                    and (_head_key(para) in heads or _head_first(para) in heads
                         or _mostly_head_words(para, head_words))) or _ornament(para):
                continue
            if len(para) <= 30 and _head_key(para) in heads and not entry:
                continue  # ponytail: Drive OCR puts the footer between the columns ("చందమామ", "జూలై 2004", 11-11)
            if not any(c.isalpha() for c in para):
                continue  # ponytail: "|" and "( |" from column rules and picture borders (11-10)
            if len(para) <= 50 and i != head_page and all(len(q) <= 50 for q in paras[:j]) \
                    and _same_title(para, open_title):
                continue  # under the page number and a figure's labels ("Economic", "(moral)")
            nd = len(re.findall("[\u0966-\u096f\u0c66-\u0c6f]", para))
            if nd >= 3 and nd >= 0.1 * len(para.replace(" ", "")):
                continue  # ponytail: books print 0-9; native digits in bulk = a picture or cover OCR'd as text
            text = re.sub(r"(?<=[a-z])- (?=[a-z])", "", para)  # "horse- shoe" -> "horseshoe"
            # ponytail: a one-word CAPS line mid-page is not a heading: on a scan with pen notes it was a
            # ghost of the handwriting ("HOW", The Feasting Dead p17, 11-21). "THE LONG WINTER" still is
            head = HEAD_WORD.match(text) or (latin and _caps_head(text) and (not placed or cur and cur[-1][0] == "h1"
                                                     or len(text.split()) >= 2)) \
                or (stories and NUMBERED.match(text))
            if contents:
                # ponytail: the book's own contents page says what the chapters are. Without it an
                # intro "Future Perfect" (not CAPS) was no chapter, while a frontispiece caption and
                # the back-cover series ads were (Jon, Unpayable Debt, 11-21)
                head = _in_contents(text, contents) and all(len(q) <= 50 for q in paras[:j])
            placed += 1
            if head and len(text) < 120 and not (toc and cur and cur[-1] == ("h1", toc.get(i))):
                if cur and head_page == i and all(k == "h1" for k, _ in cur):
                    if len(cur[-1][1].split()) <= 2 and len(text.split()) <= 2 and len(cur) == 1 and not title_done:
                        cur[-1] = ("h1", cur[-1][1] + " " + text)  # "THE FEASTING" / "DEAD": one title, one entry
                        open_title = cur[-1][1]
                        title_done = True
                    else:
                        cur.append(("p", text))  # the rest of a title page: author, publisher
                    continue
                flush()
                cur.append(("h1", text))
                head_page, open_title = i, text
            elif cur and cur[-1][0] == "p" and (text[:1].islower() and not SENT_END.search(cur[-1][1])
                                                 or re.search(r"[a-z]-$", cur[-1][1]) and text[:1].islower()):
                # ponytail: a paragraph cut by the page end or by an OCR line break goes on, not a new <p>
                prev = cur[-1][1]
                cur[-1] = ("p", prev[:-1] + text if prev.endswith("-") else prev + " " + text)
            else:
                cur.append(("p", text))
    flush()
    return chapters

def pdf_toc(doc) -> dict:
    """Top-level PDF bookmarks as {page index: title}; empty when the PDF has none."""
    try:
        # "38CaliberStoriesPart2.pdf": merged PDFs keep the file name as the bookmark
        toc = {p - 1: re.sub(r"\.pdf$", "", _clean(t).strip(), flags=re.I)[:120]
               for lvl, t, p, *_ in doc.get_toc() if lvl == 1 and p >= 1 and t.strip()}
        # a bookmark on nearly every page ("Cinema Rangam_1958_02_001", "1", "2") is a page list, not chapters
        return {} if len(toc) > max(30, len(doc) // 3) else toc
    except Exception:
        return {}


def _clean(t: str) -> str:
    # ponytail: PDF text can carry control chars, lxml refuses them in XML -> 500 on a good file
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t or "")


LINT_LOG = Path(os.environ.get("LOG_DIR", ".")) / "lint.log"


def _lint_later(pdf: bytes, epub_bytes: bytes, ref: str, pages: int):
    """Check the finished book against its PDF in the background (scripts/epub_lint.py, rules only).

    ponytail: layout defects (lost pictures, glued lists, split headings) were found only by a human
    paging through the book (Paramattha 11-21). Now every born-digital conversion leaves one line
    in lint.log: which rules fired, never the text. Files live in a temp dir and are deleted after.
    """
    if pages > 600:
        return  # a big book's check costs more than it tells; the next small one says the same

    def run():
        try:
            from scripts.epub_lint import lint
            with tempfile.TemporaryDirectory() as d:
                pp, ep = Path(d) / "in.pdf", Path(d) / "out.epub"
                pp.write_bytes(pdf)
                ep.write_bytes(epub_bytes)
                flags = lint(str(pp), str(ep))
            kinds = Counter(f.split()[0] for f in flags)
            line = json.dumps({"t": datetime.now(timezone.utc).isoformat(), "ref": ref, "pages": pages,
                               "flags": dict(kinds), "where": [f.split(":")[0][:40] for f in flags[:8]]})
            with LINT_LOG.open("a") as fh:
                fh.write(line + "\n")
        except Exception as e:  # a checker bug never touches the reader's download
            print("lint failed:", repr(e)[:200])

    threading.Thread(target=run, daemon=True).start()


def build_epub(chapters, title: str, author: str, lang: str = "en", cover: bytes | None = None) -> bytes:
    book = epub.EpubBook()
    book.set_title(_clean(title)[:120])
    if cover:
        book.set_cover("cover.jpg", cover, create_page=False)  # the library and Kindle home show it
    if author:
        book.add_author(_clean(author)[:120])
    book.set_language(lang)  # ponytail: a Kindle picks the font and hyphenation by this
    items, toc, fig_no = [], [], 0
    for i, ch in enumerate(chapters or [[("p", "empty")]]):
        # ponytail: TOC label = the chapter's own heading, else the Kindle menu shows "ch1", "ch2"
        # an untitled opening part (cover, title page, dedication) is named after the book (11-21: "ch1")
        name = next((t for k, t in ch if k in ("h1", "h2", "s2", "s3")),
                    title if i == 0 and title.strip() else f"Part {i+1}")
        c = epub.EpubHtml(title=_clean(name)[:120], file_name=f"ch{i+1}.xhtml")
        parts, sections = [], []
        for k, t in ch:
            if k == "fn":
                continue
            if k == "img":
                png, cap, em = (t + (0,))[:3] if isinstance(t, tuple) else (t, "", 0)
                fig_no += 1
                jpeg = png[:2] == b"\xff\xd8"
                fn = f"fig{fig_no}.{'jpg' if jpeg else 'png'}"
                book.add_item(epub.EpubItem(uid=f"fig{fig_no}", file_name=fn,
                                            media_type="image/jpeg" if jpeg else "image/png", content=png))
                cap_html = (f'<figcaption style="font-size:.9em;margin-top:.4em">'
                            f'{html.escape(_clean(cap))}</figcaption>') if cap else ""
                if em:  # a display equation: text-sized, not stretched to the screen
                    parts.append(f'<div style="text-align:center;margin:.6em 0">'
                                 f'<img src="{fn}" style="width:{em}em;max-width:100%;height:auto" '
                                 f'alt="Equation"/></div>')
                else:
                    parts.append(f'<figure style="text-align:center;margin:1.2em 0">'
                                 f'<img src="{fn}" style="max-width:100%;height:auto" '
                                 f'alt="Figure from the book"/>{cap_html}</figure>')
            elif k == "h1":
                parts.append(f"<h1>{html.escape(_clean(t))}</h1>")
            elif k == "h2":
                parts.append(f"<h2>{html.escape(_clean(t))}</h2>")
            elif k in ("s2", "s3"):  # a section from the PDF's own outline: anchored, listed in the contents
                sid = f"s{len(sections) + 1}"
                parts.append(f'<h{k[1]} id="{sid}">{html.escape(_clean(t))}</h{k[1]}>')
                sections.append((int(k[1]), _clean(t)[:120], sid))
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
        if sections:
            kids = []
            for lvl, t, sid in sections:
                link = epub.Link(f"ch{i+1}.xhtml#{sid}", t, f"ch{i+1}-{sid}")
                if lvl == 3 and kids:
                    head, sub = kids[-1] if isinstance(kids[-1], tuple) else (kids[-1], [])
                    kids[-1] = (head if isinstance(head, epub.Section) else
                                epub.Section(head.title, href=head.href), sub + [link])
                else:
                    kids.append(link)
            toc.append((epub.Section(_clean(name)[:120], href=f"ch{i+1}.xhtml"), kids))
        else:
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
// ponytail: a shelf key seen once (?k= or the thanks page) is kept here and sent as X-K, so
// losing the link does not drop a subscriber back to the free tier. the server still checks it
let K='';try{const k=new URLSearchParams(location.search).get('k');if(k)localStorage.setItem('k',k);K=localStorage.getItem('k')||''}catch(e){}
// ponytail: big books run as a job and the page polls, so no request hits railway's 5-minute cut.
// resolves to a url to download from; errors carry .status like a plain fetch would
async function runJob(url,fd,hdr,tick){
 const fail=(st,t)=>{const er=new Error(st+': '+t);er.status=st;return er};
 // ponytail: in-app browsers (Reddit, Instagram on Android) hand over a file they later can't read, and the
 // upload dies in under a second before reaching us. copy it into memory first, so a bad pick fails here, clearly
 const f0=fd.get('f');
 if(f0&&f0.arrayBuffer){let b;try{b=await f0.arrayBuffer()}catch(e){b=null}
  if(!b||!b.byteLength){const er=new Error('This browser could not read the file. Open epub.ftak.net in Chrome or Safari (not inside the Reddit or Instagram app), or save the PDF to your device first, then pick it again.');er.status='read';throw er}
  fd.set('f',new File([b],f0.name||'book.pdf',{type:'application/pdf'}))}
 let r;try{r=await fetch(url,{method:'POST',body:fd,headers:Object.assign({'X-Job':'1'},hdr||{})})}
 catch(e){const er=new Error('The upload did not reach the server. Check your connection and try again. If you opened this inside the Reddit or Instagram app, open epub.ftak.net in Chrome or Safari instead.');er.status='net';throw er}
 if(r.status!==202){if(!r.ok)throw fail(r.status,(await r.text()).slice(0,160));window.lastCap=r.headers.get('X-Cap')||'';return URL.createObjectURL(await r.blob())}
 const j=(await r.json()).job;
 try{localStorage.setItem('job',JSON.stringify({j:j,t:Date.now(),name:(fd.get('f')&&fd.get('f').name)||'book.pdf'}))}catch(e){}
 return pollJob(j,tick)}
// ponytail: the job id sits in localStorage, so closing the tab and opening the site again within the
// hour picks the book back up. no email provider needed
function pendingJob(){try{const p=JSON.parse(localStorage.getItem('job')||'null');
 if(p&&Date.now()-p.t<21600000)return p;localStorage.removeItem('job')}catch(e){}return null}
async function pollJob(j,tick){
 const fail=(st,t)=>{const er=new Error(st+': '+t);er.status=st;return er},t0=Date.now();
 const end=()=>{try{localStorage.removeItem('job')}catch(e){}};
 for(;;){
  await new Promise(z=>setTimeout(z,2500));
  const secs=Math.round((Date.now()-t0)/1000);if(secs>21600)throw fail(504,'took too long');
  let s;try{const q=await fetch('/job/'+j,{cache:'no-store'});if(q.status===404){end();throw fail(502,'job lost')}s=await q.json()}
  catch(e){if(e.status)throw e;continue}
  if(tick)tick(secs);
  if(s.state==='done'){end();window.lastCap=s.cap||'';return '/job/'+j+'/epub'}
  if(s.state==='error'){end();throw fail(s.status,JSON.stringify({detail:s.detail}).slice(0,200))}
 }}
// ponytail: any failure ends with "email it to us", so a broken book becomes a fixed one (and a test case)
function failHtml(e){const t=String(e&&e.message||e||'Something went wrong.'),x=t.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]);
 if(e&&e.status===429||/__SUPPORT__/.test(t))return x;
 return x+'<br><br>Email the PDF to <a href="mailto:__SUPPORT__?subject='+encodeURIComponent('PDF that failed on epub.ftak.net')+'">__SUPPORT__</a> so we can fix the converter for files like it. We rerun it once the fix is in and send you the download link.'}
function clock(n){return Math.floor(n/60)+':'+String(n%60).padStart(2,'0')}
function ev(n,x){try{navigator.sendBeacon('/e',JSON.stringify(Object.assign({n:n,v:V,src:SRC},x||{})))}catch(e){}}
ev('view',{path:location.pathname});
""".replace("__SUPPORT__", SHELF_MAIL)

PAGE_CSS = """
:root{--bg:#faf7f0;--panel:#fffdf8;--well:#f4f0e7;--line:#e4ded2;--line2:#d3ccbe;
--txt:#1b1916;--dim:#5b564d;--faint:#6f685b;--acc:#6b4ce6;--acc2:#553bc4;--ok:#1f7a4d;
--serif:"Newsreader",Georgia,"Times New Roman",serif;
--sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
--mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
*{box-sizing:border-box}
body{margin:0;color:var(--txt);font-family:var(--sans);-webkit-font-smoothing:antialiased;
background:linear-gradient(var(--line),var(--line)) calc(50% - 490px) 0/1px 100% no-repeat,
linear-gradient(var(--line),var(--line)) calc(50% + 490px) 0/1px 100% no-repeat,var(--bg)}
html{scroll-behavior:smooth;scroll-padding-top:84px}
::selection{background:#e4dcff;color:var(--txt)}
code,.mono{font-family:var(--mono)}
.wrap{max-width:940px;margin:0 auto;padding:0 20px 72px}
a{color:var(--acc2)}
header.top{position:sticky;top:12px;z-index:20;display:flex;align-items:center;gap:6px;
max-width:640px;margin:14px auto 0;padding:7px 7px 7px 18px;border:1px solid var(--line);border-radius:99px;
background:rgba(255,253,248,.84);-webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);
box-shadow:0 10px 30px -18px rgba(40,30,90,.35)}
.navl{display:flex;gap:2px;margin-left:auto}
.navl a{white-space:nowrap;color:var(--dim);text-decoration:none;font-size:13.5px;padding:7px 10px;border-radius:99px}
.navl a:hover{color:var(--txt);background:var(--well)}
.navgo{background:var(--txt);color:var(--panel);text-decoration:none;font-size:13.5px;font-weight:600;
padding:9px 16px;border-radius:99px;white-space:nowrap}
.navgo:hover{background:var(--acc2)}
.navl a:focus-visible,.navgo:focus-visible,.mark:focus-visible{outline:2px solid var(--acc2);outline-offset:2px}
.mark{color:var(--txt);text-decoration:none;display:flex;align-items:baseline;gap:9px;font-family:var(--serif);font-weight:500;
letter-spacing:-.2px;font-size:19px}
.mark .dot{width:8px;height:8px;border-radius:50%;background:var(--acc);align-self:center}
.mark .to{color:var(--faint);font-weight:400;font-size:13px;letter-spacing:0}
.pill{font-family:var(--mono);font-size:11.5px;color:var(--dim);border:1px solid var(--line);
border-radius:99px;padding:5px 11px}
.pill b{color:var(--ok);font-weight:500}
.hero{text-align:center;padding:44px 0 0}
h1{font-family:var(--serif);font-size:clamp(40px,7vw,66px);line-height:1.04;
letter-spacing:-.035em;margin:0 auto;font-weight:400;text-wrap:balance}
h1 .em{color:var(--acc)}
.lede{color:var(--dim);font-size:clamp(15.5px,1.9vw,18px);line-height:1.6;margin:16px auto 0;max-width:46ch}
.facts{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin:20px 0 0}
.fact{font-family:var(--mono);font-size:12px;color:var(--dim);border:1px solid var(--line);
border-radius:4px;padding:6px 10px}
.fact b{color:var(--txt);font-weight:500}
.stage{margin-top:30px;padding:20px;border-radius:20px;border:1px solid var(--line);
background:radial-gradient(70% 90% at 0% 0%,#ddd2ff 0%,rgba(221,210,255,0) 70%),
radial-gradient(60% 80% at 100% 100%,#f7d6bd 0%,rgba(247,214,189,0) 70%),
linear-gradient(160deg,#ece5fa,#f5ede4)}
.stage .card{border-color:rgba(27,25,22,.08);border-radius:10px;
box-shadow:0 1px 2px rgba(27,25,22,.05),0 24px 48px -28px rgba(50,30,130,.45)}
.reads{text-align:center;font-size:12px;color:var(--faint);margin:18px 0 0;letter-spacing:.02em}
.reads i{display:inline-block;width:3px;height:3px;border-radius:50%;background:var(--line2);vertical-align:middle;margin:0 10px}
.grid2{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);gap:16px}
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
#next{margin-top:14px;padding-top:12px;border-top:1px dashed var(--line2)}
#next .next-q{font-size:13.5px;color:var(--dim);margin:0 0 4px}
#next .ghost-btn.on{color:var(--txt);border-color:var(--txt)}
#wantf{margin-top:10px}
.proof .rows{margin:0;padding:0;list-style:none;border-top:1px solid var(--line)}
.proof .rows li{display:flex;gap:12px;justify-content:space-between;align-items:baseline;
padding:9px 0;border-bottom:1px solid var(--line);font-size:13px}
.proof .rows .k{color:var(--faint)}
.proof .rows .v{color:var(--txt);font-family:var(--mono);font-size:12px;text-align:right}
h2{font-family:var(--serif);font-size:19px;font-weight:500;letter-spacing:-.2px;margin:42px 0 14px}
.fixes{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.fix{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.fx{padding:14px 16px 16px}
.fix b{display:block;font-family:var(--serif);font-size:17px;line-height:1.25;font-weight:500}
.fix p{margin:6px 0 0;font-size:13.5px;line-height:1.55;color:var(--dim)}
.viz{height:118px;display:flex;align-items:center;justify-content:center;gap:14px;border-bottom:1px solid var(--line)}
.v-para{background:linear-gradient(160deg,#e6defd,#f3eefc)}
.v-toc{background:linear-gradient(160deg,#f8e2d1,#fbf0e6)}
.v-scan{background:linear-gradient(160deg,#dcebe2,#eef5f0)}
.viz .pg{width:58px;height:78px;background:var(--panel);border-radius:3px;padding:10px 8px;display:flex;flex-direction:column;gap:5px;
box-shadow:0 1px 2px rgba(27,25,22,.08),0 10px 20px -12px rgba(27,25,22,.35)}
.viz .pg i{display:block;height:3px;border-radius:2px;background:#d3ccbe}
.v-para .pg:first-child i:nth-child(odd){width:62%}.v-para .pg:first-child i:nth-child(even){width:80%}
.v-para .book1 i{background:var(--acc);opacity:.55}.v-para .book1 i:first-child{margin-left:9px}
.v-toc .pg{width:70px}.v-toc .pg i{position:relative;margin-left:9px;width:calc(100% - 9px)}
.v-toc .pg i::before{content:"";position:absolute;left:-9px;top:-1px;width:5px;height:5px;border-radius:50%;background:#d98a52}
.v-toc .pg i:nth-child(2){width:60%}.v-toc .pg i:nth-child(4){width:72%}
.v-scan .scan{transform:rotate(-4deg);background:repeating-linear-gradient(180deg,#b9b4a8 0 2px,transparent 2px 7px),
linear-gradient(135deg,#e9e4d8,#cfc9bb);filter:blur(.4px)}
.v-scan .pg:last-child i{background:#1f7a4d;opacity:.5}
.fix .tag{display:block;font-family:var(--mono);font-size:11px;letter-spacing:.06em;
text-transform:uppercase;color:var(--acc);margin-bottom:6px}
.links{display:flex;flex-wrap:wrap;gap:9px;margin-top:34px}
.links a{font-size:13px;text-decoration:none;border:1px solid var(--line2);border-radius:4px;
padding:9px 12px;color:var(--dim);background:var(--panel);transition:border-color .15s,color .15s}
.links a:hover{color:var(--txt);border-color:#bdb4a4}
footer{margin-top:34px;padding-top:16px;border-top:1px solid var(--line);color:var(--faint);
font-size:12.5px;display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center}
footer .mono{font-size:11.5px}
.pane-t{display:flex;justify-content:space-between;gap:10px;font-size:12px;color:var(--faint);margin:0 0 7px}
.pane-t .v{font-family:var(--mono);font-size:11.5px}
.pdfpage{background:var(--well);border:1px solid var(--line);border-radius:4px;padding:10px 14px 9px;font-family:var(--serif)}
.pdfpage .cut{display:flex;justify-content:space-between;gap:10px;font-size:10.5px;color:var(--faint)}
.pdfpage .cut em{font-style:normal;font-family:var(--sans);font-size:11px}
.pdfpage h3,.book h3{font-family:var(--serif);font-size:14px;font-weight:600;margin:8px 0 3px}
.ln{display:flex;gap:8px;font-size:12px;line-height:1.6;color:var(--dim)}
.ln span{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ln i{font-style:normal;color:var(--faint);font-family:var(--sans)}
.ln:last-of-type{margin-bottom:6px}
.book{background:var(--panel);border:1px solid var(--line2);border-radius:4px;padding:11px 14px 13px}
.book h3{margin-top:0}
.book p{font-family:var(--serif);font-size:13.5px;line-height:1.6;margin:0;text-indent:1.3em;color:var(--txt)}
.book h3+p{text-indent:0}
.said{display:grid;grid-template-columns:1.05fr .95fr;gap:16px;align-items:start}
.said figure{margin:0}
.said .qs{display:grid;gap:22px}
.said .q2 blockquote{font-size:clamp(18px,2.2vw,21px);line-height:1.35}
.said blockquote{margin:0;font-family:var(--serif);font-size:clamp(24px,3.2vw,30px);line-height:1.2;letter-spacing:-.015em}
.said figcaption{margin-top:10px;font-size:13px;color:var(--faint)}
.said .feat{margin:0;font-size:14px;line-height:1.6;color:var(--dim);border-left:1px solid var(--line2);padding:2px 0 2px 16px}
.said .feat b{color:var(--txt);font-weight:600}
.prices{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.price{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:16px;display:flex;flex-direction:column}
.price h3{font-family:var(--serif);font-size:15px;font-weight:600;margin:0}
.price .amt{font-family:var(--mono);font-size:12.5px;color:var(--txt);margin:3px 0 10px}
.price p{margin:0 0 14px;font-size:13px;line-height:1.55;color:var(--dim);flex:1}
.price a{display:block;text-align:center;text-decoration:none;border:1px solid var(--line2);border-radius:6px;
padding:10px 14px;font-size:13px;color:var(--txt);transition:border-color .15s}
.price a:hover{border-color:var(--acc)}
.price .here{font-size:13px;color:var(--faint);padding:10px 0;border-top:1px solid var(--line)}
.faq{border-top:1px solid var(--line);max-width:70ch}
.faq details{border-bottom:1px solid var(--line)}
.faq summary{cursor:pointer;list-style:none;display:flex;justify-content:space-between;gap:16px;
padding:13px 0;font-size:15px;font-weight:600}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";color:var(--faint);font-weight:400}
.faq details[open] summary::after{content:"\\2212"}
.faq summary:focus-visible{outline:2px solid var(--acc2);outline-offset:2px}
.faq p{margin:0 0 14px;font-size:14px;line-height:1.6;color:var(--dim)}
.end{margin-top:44px;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:14px 24px;
background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:20px}
.end p{margin:0;font-family:var(--serif);font-size:22px;letter-spacing:-.01em}
.end .go{width:auto;margin:0;padding:13px 28px}
@media(max-width:720px){.grid2{grid-template-columns:minmax(0,1fr)}.fixes{grid-template-columns:1fr}
.said,.prices{grid-template-columns:1fr}.said .feat{border-left:0;padding:0}
h1{letter-spacing:-.015em}}
@media(max-width:1020px){body{background:var(--bg)}}
@media(max-width:560px){header.top{padding:6px 6px 6px 14px;margin-top:10px}.navl{display:none}.navgo{margin-left:auto}
.hero{padding-top:30px}.facts .fact:first-child,.facts .fact:nth-child(4){display:none}.stage{padding:10px;border-radius:14px;margin-top:32px}.pill{display:none}.card{padding:16px}}
"""

PAGE_HEAD = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/fonts.css">
<title>PDF to EPUB - real chapters, real paragraphs, free</title>
<meta name="description" content="Free PDF to EPUB with real chapters, a clickable table of contents, scanned books read with OCR. No signup, no watermark, nothing stored.">
<meta property="og:title" content="PDF to EPUB - real chapters, real paragraphs, free">
<meta property="og:description" content="No signup, no watermark, nothing stored. Scans read with OCR.">
__ALT__
<script type="application/ld+json">__FAQLD__</script>
<style>__CSS__</style>__CFB__</head><body><div class="wrap">
<header class="top">
  <a class="mark" href="#top"><span class="dot"></span>pdf2epub</a>
  <nav class="navl"><a href="#prices">Prices</a><a href="#faq">Questions</a><a href="/guides">Guides</a></nav>
  <a class="navgo" href="#drop" id="navgo">Convert a PDF</a>
</header>

<section class="hero" id="top">
<h1>Your PDF, as a <span class="em">real book</span>.</h1>
<p class="lede">Real chapters, real paragraphs. Free, no signup, nothing kept.</p>
<div class="facts mono">
  <span class="fact">files not stored &middot; <b>no account</b></span>
  <span class="fact"><b>1GB</b> / 150 pages</span>
  <span class="fact">Scans: OCR free for <b>__FREEOCR__ pages</b></span>
  <span class="fact">EPUB3, Kindle, Kobo, Apple Books</span>
  <span class="fact" id="st" hidden></span>
</div>

</section>

<div class="stage"><div class="grid2">
  <div class="card convert">
    <h2>Convert a PDF</h2>
    <div id="drop" class="drop"><b>Drop a PDF here</b><span>or click to choose one</span></div>
    <input id="file" type="file" accept=".pdf,.djvu,.djv" hidden>
    <div class="row">
      <input id="title" placeholder="Title (optional)" maxlength="120">
      <input id="author" placeholder="Author (optional)" maxlength="120">
    </div>
    <div class="row"><input id="email" placeholder="Email (optional) - for big files and the paid tier"></div>
    <button class="go" id="go">Convert to EPUB</button>
    <button class="ghost-btn" id="sample">Try it with a sample PDF</button>
    <div id="msg"></div>
    <div id="next" hidden>
      <p class="next-q">Four things I might build next. Want one?</p>
      <button class="ghost-btn" data-want="kindle">Send it to my Kindle by email, no cable</button>
      <button class="ghost-btn" data-want="translate">Translate this book into another language</button>
      <button class="ghost-btn" data-want="desktop">Mac app: converts offline, no page limit</button>
      <button class="ghost-btn" data-want="audio">Listen to this book: audiobook with a voice per character</button>
      <form id="wantf" hidden>
        <p class="next-q">Not built yet. Leave your email and you will hear first if it ships.</p>
        <div class="row"><input id="wante" type="email" required placeholder="Your email" maxlength="120"></div>
        <button class="go" type="submit">Notify me</button>
      </form>
      <p class="next-q" id="wantok" hidden>Thanks. You are on the list.</p>
    </div>
  </div>

  <div class="card proof">
    <h2>The actual output</h2>
    <div class="pane-t"><span>The sample PDF, page 1</span><span class="v">__PARAS__ printed lines</span></div>
    <div class="pdfpage">
      <div class="cut"><s>__RUNHEAD__</s><em>removed</em></div>
      <h3>__HEAD1__</h3>
      __PDFLINES__
      <div class="cut"><s>__PAGENO__</s><em>removed</em></div>
    </div>
    <div class="pane-t" style="margin-top:12px"><span>The same page in the EPUB</span><span class="v">__EPARAS__ paragraphs, __TOCN__ chapters</span></div>
    <div class="book"><h3>__HEAD1__</h3>__BOOKPARAS__</div>
  </div>
</div></div>
<p class="reads mono" aria-label="Opens on">Kindle <i></i> Kobo <i></i> Apple Books <i></i> Boox <i></i> KOReader</p>

<h2>What it repairs</h2>
<div class="fixes">
  <div class="fix"><div class="viz v-para" aria-hidden="true"><div class="pg"><i></i><i></i><i></i><i></i></div><div class="pg book1"><i></i><i></i><i></i></div></div>
    <div class="fx"><span class="tag">paragraphs</span><b>One paragraph per paragraph</b>
    <p>Lines the PDF broke at the page edge join back into whole paragraphs.</p></div></div>
  <div class="fix"><div class="viz v-toc" aria-hidden="true"><div class="pg"><i></i><i></i><i></i><i></i><i></i></div></div>
    <div class="fx"><span class="tag">chapters</span><b>Headings become chapters</b>
    <p>Your reader gets a table of contents you can tap to jump between chapters.</p></div></div>
  <div class="fix"><div class="viz v-scan" aria-hidden="true"><div class="pg scan"></div><div class="pg"><i></i><i></i><i></i><i></i></div></div>
    <div class="fx"><span class="tag">scans</span><b>Scans get OCR</b>
    <p>Photographed pages are read into real text you can search and resize.</p></div></div>
</div>

<h2>From readers</h2>
<div class="said">
  <div class="qs">
  <figure><blockquote>&ldquo;The footnotes look great.&rdquo;</blockquote>
    <figcaption>A reader, after converting a 497-page book</figcaption></figure>
  <figure class="q2"><blockquote>&ldquo;My 320-page book with 150+ pictures came out at 23&nbsp;MB with no embedded fonts and went straight into Draft2Digital.&rdquo;</blockquote>
    <figcaption>A self-published author, whose own Pages export was over 100&nbsp;MB</figcaption></figure>
  </div>
  <p class="feat">Featured in the <b>deepculture</b> newsletter, issue #243. One of its readers converted 68 books in 32 minutes.</p>
</div>

<h2 id="prices">Prices</h2>
<div class="prices">
  <div class="price"><h3>Free</h3><div class="amt">$0</div>
    <p>One PDF at a time, up to 150 pages and 1GB. Scans up to __FREEOCR__ pages.</p>
    <span class="here">It is the converter above</span></div>
  <div class="price"><h3>One book</h3><div class="amt">$5 once</div>
    <p>One book up to 2,000 pages, scans included. Pay, come back to an upload box, convert on the spot.</p>
    <a href="/go/onebook?why=landing" data-go>Pay $5 for one book</a></div>
  <div class="price"><h3>Shelf</h3><div class="amt">$10 a month</div>
    <p>No monthly limit. Any number of books, each up to 2,000 pages, scans included.</p>
    <p>Or $10 once for 30 days, no renewal.</p>
    <a href="/shelf">See Shelf</a></div>
</div>
<p class="refund" style="font-size:14px;color:#5b564d;margin-top:10px">Not happy with the book? Full refund within 30 days, no questions asked.</p>

<h2 id="faq">Questions</h2>
<div class="faq">__FAQ__</div>

<div class="end">
  <p>Drop a PDF, get a book back.</p>
  <button class="go" id="again">Convert a PDF</button>
</div>

<div class="links">
  <a href="/scan">Scan a physical book with your phone</a>
  <a href="https://ftak.net/translate-pdf">Translate a PDF into another language</a>
  <a href="/shelf">Shelf: $10/mo, no monthly limit</a>
  <a href="/guides/scanned-pdf-to-epub">Scanned PDF to EPUB</a>
  <a href="/guides/send-pdf-to-kindle">PDF to Kindle, Kobo, Boox</a>
  <a href="/guides/pdf-to-epub-vs-calibre">vs Calibre</a>
  <a href="/guides">Guides</a>
  <a href="/privacy">Privacy</a>
  <a href="/" hreflang="en" lang="en">English</a>
  <a href="/pt/" hreflang="pt" lang="pt-BR">Português</a>
  <a href="/es/" hreflang="es" lang="es">Español</a>
</div>

<footer>
  <span>No account &middot; no watermark &middot; files deleted after download</span>
  <form id="keyform" action="/" method="get" style="margin-top:10px;font-size:14px">
    <label for="kin">Paid on another device? Paste your key:</label>
    <input id="kin" name="k" pattern="[0-9A-Za-z_-]{6,64}" required autocomplete="off" style="font:inherit;padding:4px 6px;width:15em">
    <button type="submit" style="font:inherit">Use key</button>
  </form>
</footer>
</div><script>
__TRACK__const drop=document.getElementById('drop'),fi=document.getElementById('file'),
 msg=document.getElementById('msg'),go=document.getElementById('go'),smp=document.getElementById('sample');
const BTN='display:inline-block;margin:8px 8px 0 0;background:#6b4ce6;color:#fff;border:0;border-radius:4px;'
 +'padding:10px 16px;font:inherit;font-weight:650;cursor:pointer;text-decoration:none';
const GHOST='display:inline-block;margin:8px 8px 0 0;background:transparent;color:#5b564d;border:1px solid #d3ccbe;'
 +'border-radius:4px;padding:9px 14px;font:inherit;cursor:pointer;text-decoration:none';
// ponytail: no accounts, so the browser remembers the paid checkout and the landing points back to it
try{const ob=localStorage.getItem('onebook');if(ob){msg.className='ok';msg.innerHTML='You have a paid book waiting. '
 +'<a href="/onebook?checkout_id='+encodeURIComponent(ob)+'">Convert it here</a>'}}catch(e){}
function buy(why){return '/go/onebook?why='+why+'&v='+V}
// ponytail (11-10 test): a book up to 400 pages gets the $3 offer instead of $5; 'short' clicks in /funnel
function short(n){return n&&+n<=400}
function buy3(why){return '/go/short?why='+why+'&v='+V}
// ponytail: the free converter refuses big files, so the refusal is where the paid tier gets pitched
// ponytail (11-07): over the limit we convert the free part first, so the $5 ask comes after they've seen their own book
// ponytail (11-12): first whole book free for an email, once per browser.
// ponytail (11-14): moved under the paid button: the $5 at the wall is the one sale that came on its own
// (11-03), and with the free box on top 17 wall hits in 2.5 days left 1 email, 0 sales
function fbUsed(){try{return !!localStorage.getItem('fb_used')}catch(e){return false}}
function freeOffer(n){return fbUsed()?'':'<div style="margin:12px 0 6px;padding:10px 14px;background:#efeafd;border-radius:6px;font-size:14px">'
 +'<b>New here? Your first whole book is free.</b> Leave your email and all '+(n||'')+' pages convert now. '
 +'We may write once to ask how it came out.<br>'
 +'<input id="fbmail" type="email" placeholder="your email" '
 +'style="max-width:300px;margin-top:8px;background:#fff;border:1px solid #d3ccbe;color:#1b1916;'
 +'border-radius:4px;padding:10px 12px;font:inherit;font-size:14px"> '
 +'<button id="fbbtn" style="'+GHOST+'">Convert it free</button></div>'}
// ponytail (11-16): a reader who hits the wall with a 2nd book in one visit is a multi-book reader (the only
// buyers who come back: Shelf, Batch). 11-15 two of them left with no email (3 books in 4 min, 1,070 + 568 p).
// From the 2nd walled file on, the free-book email box and the $10/30-day pass go on top of the pitch.
function wallFiles(){try{return JSON.parse(sessionStorage.getItem('walls')||'[]')}catch(e){return window._walls||[]}}
function multi(){const w=wallFiles(),nm=window.capName||'book';
 if(w.indexOf(nm)<0){w.push(nm);window._walls=w;try{sessionStorage.setItem('walls',JSON.stringify(w))}catch(e){}
  if(w.length>=2)ev('multi_wall',{why:String(w.length)})}
 return w.length>=2?w.length:0}
function multiBox(n,k){return '<div style="margin:0 0 12px;padding:12px 14px;border:2px solid #6b4ce6;border-radius:6px">'
 +'<b>Converting several books?</b> This is your '+(k===2?'second':k===3?'third':k+'th')+' over the free limit today.<br>'
 +'<a style="'+BTN+'" href="/go/batch?why=multi&v='+V+'">$10 for 30 days, every book, no renewal</a></div>'}
// ponytail (11-22): over the limit there is no free part any more. Both wall sales (11-03 $5, 11-04 Shelf)
// came from the hard wall (2 of 18 wall readers); since the free 150-page preview (11-07) 0 of 136 paid.
function seen(){return window.previewDone?'Your first '+PN+' pages are downloaded. Open the EPUB and check the paragraphs and chapters.<br>':''}
function pitchPages(n){const k=multi();return seen()+(k?multiBox(n,k):'')+'This PDF has '+(n||'over 150')+' pages. The free converter stops at 150.<br>'
 +(short(n)?'<a style="'+BTN+'" href="'+buy3(window.previewDone?'pages-seen':'pages')+'">Convert the whole book - $3</a>'
  :'<a style="'+BTN+'" href="'+buy(window.previewDone?'pages-seen':'pages')+'">Convert the whole book - $5</a>')
 +'<a style="'+GHOST+'" href="/go/shelf?why=pages&v='+V+'">A whole shelf? $10/month</a>'
 +'<br><span style="font-size:16px"><b>Not happy with the book? Full refund, no questions asked.</b></span>'
 +'<br><span style="font-size:13px;color:#5b564d">Pay once, you come straight back here and the book converts '
 +'on the spot, up to 2,000 pages. Nothing stored.</span>'
 +'<br><br><span style="font-size:13px;color:#5b564d">Bigger than 2,000 pages? Still $5. Leave your email and we raise the limit for your book.</span><br>'
 +'<input id="leadmail" type="email" placeholder="your email" '
 +'style="max-width:340px;background:#f4f0e7;border:1px solid #e4ded2;color:#1b1916;'
 +'border-radius:4px;padding:10px 12px;font:inherit;font-size:14px"> '
 +'<button id="leadbtn" style="'+BTN+'">Ask</button>'}
function pitchOcr(n){const k=multi();return seen()+(k?multiBox(n,k):'')+'This is a scan ('+(n||'many')+' pages), so every page has to be read with OCR. '
 +'Free OCR covers __FREEOCR__ pages.<br>'
 +(short(n)?'<a style="'+BTN+'" href="'+buy3(window.previewDone?'ocr-seen':'ocr')+'">OCR the whole book - $3</a>'
  :'<a style="'+BTN+'" href="'+buy(window.previewDone?'ocr-seen':'ocr')+'">OCR the whole book - $5</a>')
 +'<br><span style="font-size:16px"><b>Not happy with the book? Full refund, no questions asked.</b></span>'
 +'<br><span style="font-size:13px;color:#5b564d">Pay once, you come straight back here and the book converts '
 +'on the spot. Nothing stored.</span>'}
document.addEventListener('click',async(e)=>{
 if(e.target.id==='preview'){PN=e.target.dataset.n;convert(true);return}
 if(e.target.id==='fbbtn'){const em=document.getElementById('fbmail');
  if(!em||!em.value){em&&em.focus();return}
  e.target.disabled=true;ev('freebook_ask');
  const fd=new FormData();fd.append('email',em.value);if(window.capPages)fd.append('pages',window.capPages);
  const r=await fetch('/freebook',{method:'POST',body:fd});const j=await r.json().catch(()=>({}));
  if(r.ok&&j.token){window.FREE=j.token;try{localStorage.setItem('fb_used','1')}catch(x){}
   if(!document.getElementById('email').value)document.getElementById('email').value=em.value;
   ev('freebook');window.previewDone=false;window.capKind='';return convert(false)}
  e.target.disabled=false;
  em.insertAdjacentHTML('afterend',j.why==='email'?'<br><span style="color:#a33">That email does not look right.</span>'
   :'<br><span style="color:#a33">That email already had its free book. The next one is $5, or $10 for 30 days of unlimited books.</span>');
  return}
 if(e.target.id!=='leadbtn')return;
 const em=document.getElementById('leadmail');
 if(!em||!em.value)return;
 e.target.disabled=true;ev('lead');
 const fd=new FormData();fd.append('email',em.value);fd.append('reason','cap');
 if(window.capPages)fd.append('pages',window.capPages);
 const r=await fetch('/lead',{method:'POST',body:fd});
 msg.className='ok';msg.innerHTML=r.ok
  ?'Got it. Email the PDF to <a href="mailto:__MAIL__?subject='+encodeURIComponent('PDF to EPUB - '+(window.capName||'book'))+'">__MAIL__</a> with the page count and we will raise the limit for your book, same $5.'
  :'Put an email in the box first.';
 e.target.disabled=false;});
drop.onclick=()=>fi.click();
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.add('over')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.remove('over')}));
drop.addEventListener('drop',x=>{fi.files=x.dataTransfer.files;if(fi.files[0]){ev('pick');djvuDoor()}});
fi.addEventListener('change',()=>{if(fi.files[0]){ev('pick');drop.querySelector('b').textContent=fi.files[0].name;djvuDoor()}});
// ponytail (11-16): djvu fake door. google trends has "djvu to epub" +350% (scanned books, same readers as our OCR
// payers). nothing is uploaded: a djvu pick asks for an email, and 5+ picks/emails in 14 days decide if it gets built
const isDjvu=f=>!!f&&/\.djvu?$/i.test(f.name||'');
function djvuDoor(){const f=fi.files[0];if(!isDjvu(f))return false;
 ev('djvu_pick');msg.className='';
 msg.innerHTML='<b>'+esc(f.name)+'</b> is a DjVu file. We don\\'t convert DjVu yet, and we\\'re deciding whether to build it now.'
  +'<br>Leave your email and we convert this book to EPUB for free when DjVu is ready.'
  +'<form id="djf" style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap"><input id="dje" type="email" required placeholder="you@email.com" style="flex:1;min-width:180px">'
  +'<button type="submit">Notify me</button></form>';
 document.getElementById('djf').onsubmit=async e=>{e.preventDefault();const fd=new FormData();
  fd.append('email',document.getElementById('dje').value);fd.append('reason','want:djvu');
  try{await fetch('/lead'+location.search,{method:'POST',body:fd})}catch(x){}
  ev('want_email',{why:'djvu'});msg.className='ok';msg.textContent='Thanks. We\\'ll email you when DjVu works, and this book converts free.'};
 return true}
// ponytail (11-10): a Shelf reader with 1,000 Telugu novels asked for this. With a Shelf key, pick many
// PDFs or a whole folder: they convert one by one on the normal job path and each EPUB downloads as it finishes
let BATCH=[];
const esc=t=>String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]);
function pickMany(list){BATCH=list.filter(f=>/\.pdf$/i.test(f.name||''));
 if(BATCH.length>1){drop.querySelector('b').textContent=BATCH.length+' PDFs picked';ev('pick',{why:'batch'})}}
// ponytail (11-14): the key lives in one browser's storage; a buyer who paid on an iPad got the free tier on
// their Mac (ysvsr). the footer box puts the key on this browser too; with a key, it says so instead
if(K){const kf=document.getElementById('keyform');if(kf)kf.innerHTML='Paid key active in this browser.';}
if(K){fi.multiple=true;
 const fb=document.createElement('input');fb.type='file';fb.webkitdirectory=true;fb.multiple=true;fb.hidden=true;
 const bb=document.createElement('button');bb.className='ghost-btn';bb.id='folder';bb.type='button';
 bb.textContent='Choose a whole folder';go.after(bb);bb.after(fb);
 bb.onclick=()=>fb.click();fb.onchange=()=>pickMany([...fb.files]);
 fi.addEventListener('change',()=>pickMany([...fi.files]));
 drop.addEventListener('drop',x=>pickMany([...x.dataTransfer.files]))}
async function convertMany(){
 go.disabled=true;const ok=[],bad=[],n=BATCH.length;ev('submit',{why:'batch'});
 const failed=()=>bad.map(b=>esc(b[0])+' - '+esc(b[1])).join('<br>');
 const show=(i,name)=>{msg.className='';msg.innerHTML='Book '+(i+1)+' of '+n+': '+esc(name)+'<br>'+ok.length+' done'
  +(bad.length?', '+bad.length+' failed':'')+'. Keep this tab open. If the browser asks to allow multiple downloads, allow it.'
  +(bad.length?'<br><br>Failed so far:<br>'+failed():'')};
 for(let i=0;i<n;i++){const f=BATCH[i];show(i,f.name);
  const fd=new FormData();fd.append('f',f);fd.append('title','');fd.append('author','');
  fd.append('email',document.getElementById('email').value);
  try{const u=await runJob('/convert'+location.search,fd,{'X-V':V,'X-K':K},s=>show(i,f.name+' ('+clock(s)+')'));
   const a=document.createElement('a');a.href=u;a.download=f.name.replace(/\.pdf$/i,'')+'.epub';
   document.body.appendChild(a);a.click();a.remove();ok.push(f.name);ev('done',{why:'batch'})}
  catch(e){const m=String(e&&e.message||e);bad.push([f.name,((m.match(/"detail":"([^"]+)"/)||[])[1]||m).slice(0,140)]);ev('fail',{status:String(e&&e.status||'net'),why:'batch'})}
  await new Promise(z=>setTimeout(z,800))}
 msg.className=bad.length?'err':'ok';
 msg.innerHTML='All done: '+ok.length+' of '+n+' converted.'+(bad.length?'<br><br>These did not convert. Email them to '
  +'<a href="mailto:__MAIL__">__MAIL__</a> and we fix the converter for them:<br>'+failed():'');
 go.disabled=false}
let PN='__FREEOCR__';
(async()=>{const p=pendingJob();if(!p)return;
 msg.className='';msg.textContent='Picking up '+p.name+' where you left it...';go.disabled=true;
 try{const u=await pollJob(p.j,n=>{msg.textContent='Still converting '+p.name+' ('+clock(n)+')...'});
  const a=document.createElement('a');a.href=u;a.download=p.name.replace(/\.pdf$/i,'')+'.epub';a.click();ev('done',{why:'resume'});
  msg.className='ok';msg.textContent='Done. '+p.name.replace(/\.pdf$/i,'')+'.epub downloaded.'}
 catch(e){msg.className='err';if(e.status===502)msg.textContent='That conversion is gone (over an hour old). Upload it again.';else msg.innerHTML=failHtml(e)}
 go.disabled=false})();
async function convert(preview){
 const f=fi.files[0];
 if(!f){msg.className='err';msg.textContent='Choose a PDF first.';return}
 if(djvuDoor())return;
 msg.className='';msg.textContent=preview?'Reading the first '+PN+' pages...':'Converting...';go.disabled=true;
 ev('submit',preview?{why:'preview'}:{});
 const fd=new FormData();fd.append('f',f);
 fd.append('title',document.getElementById('title').value);
 fd.append('author',document.getElementById('author').value);
 fd.append('email',document.getElementById('email').value);
 // ponytail: always ask for the free part, so an over-limit book uploads once (not refused, then re-sent)
 if(preview)fd.append('preview','1');window.lastCap='';
 if(window.FREE)fd.append('free',window.FREE);
 try{
  const u=await runJob('/convert'+location.search,fd,{'X-V':V,'X-K':K},n=>{if(n>=20)msg.textContent='Still converting ('+clock(n)
   +'). Big books and scans take a few minutes. If you close this tab, open epub.ftak.net again within the hour and it picks up'
   +(document.getElementById('email').value?', or use the link I email you.':'.')});
  const a=document.createElement('a');a.href=u;
  a.download=(f.name||'book').replace(/\.pdf$/i,'')+'.epub';a.click();ev('done');showNext();
  msg.className='ok';msg.textContent=preview?'Done. The preview EPUB has the first '+PN+' pages.':'Done. EPUB downloaded.'
  if(window.FREE&&!preview){window.FREE='';msg.innerHTML='Done. The whole book is downloaded, that one was on us.<br>'
   +'<span style="font-size:14px">More books coming? <a href="/go/batch?why=freebook-done&v='+V+'">$10 for 30 days, unlimited books</a>'
   +' or <a href="/go/onebook?why=freebook-done&v='+V+'">$5 for the next one</a>.</span>';ev('free_done')}
  const lc=(window.lastCap||'').split(':');
  if(!preview&&(lc[0]==='pages'||lc[0]==='ocr')){window.capKind=lc[0];window.capPages=+lc[1]||0;window.capName=(f&&f.name)||'book';
   PN=lc[0]==='pages'?'150':'__FREEOCR__';ev('preview_auto',{why:lc[0]});preview=true}
  if(preview&&window.capKind){window.previewDone=true;msg.className='';
   msg.innerHTML=window.capKind==='ocr'?pitchOcr(window.capPages):pitchPages(window.capPages);ev('pitch',{why:window.capKind+'-seen'})}}
 catch(e){msg.className='err';msg.innerHTML=failHtml(e);ev('fail',{status:String(e.status||'net')});
  const n=+(e.message.match(/\((\d+) here\)/)||[])[1]||0;
  const cap=e.status===413&&!K?'pages':(e.status===402&&/scanned/.test(e.message)?'ocr':'');
  // over the limit on a full run: convert the free part straight away instead of asking first
  if(!preview){window.capPages=n;window.capName=(f&&f.name)||'book'}
  if(e.status===413&&!K){msg.className='';msg.innerHTML=pitchPages(n);ev('pitch',{why:'pages'})}
  else if(e.status===502||e.status===503||e.status===504){msg.innerHTML='This file was too heavy for the instant converter. That is on our side, not your file.'
   +'<br><br>Email the PDF to <a href="mailto:__MAIL__">__MAIL__</a> so we can rerun it on the big-file converter and send you the download link.'}
  if(e.status===402&&/scanned/.test(e.message)){msg.className='';msg.innerHTML=pitchOcr(n);ev('pitch',{why:'ocr'})}}
 go.disabled=false}
go.onclick=()=>BATCH.length>1?convertMany():convert(false);
smp.onclick=async()=>{
 msg.className='';msg.textContent='Converting the sample...';smp.disabled=true;go.disabled=true;ev('sample');
 try{
  const b=await (await fetch('/sample.pdf')).blob();
  const fd=new FormData();fd.append('f',new File([b],'sample.pdf',{type:'application/pdf'}));
  fd.append('title','Sample Book');fd.append('email',document.getElementById('email').value);
  const r=await fetch('/convert'+location.search,{method:'POST',body:fd,headers:{'X-V':V,'X-K':K}});
  if(!r.ok){const t=await r.text();throw new Error(r.status+': '+t.slice(0,140))}
  const blob=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='sample.epub';a.click();
  msg.className='ok';msg.textContent='Done. Open sample.epub and check the chapter list.'}
 catch(e){msg.className='err';msg.innerHTML=failHtml(e)}
 smp.disabled=false;go.disabled=false};
fetch('/stats').then(r=>r.json()).then(s=>{const el=document.getElementById('st');
 if(s.conversions_ok>=50){el.textContent=s.conversions_ok+' books converted';el.hidden=false}}).catch(()=>{});
document.querySelectorAll('[data-go]').forEach(a=>a.href+='&v='+V);
// ponytail: which objection people open is the cheapest research we get
document.querySelectorAll('.faq details').forEach((d,i)=>d.addEventListener('toggle',()=>{if(d.open)ev('faq',{why:'q'+(i+1)})}));
// fake doors (11-07, audio 11-08): translation, a Mac app and audiobooks are not built; clicks + emails decide if they get built
let WANT='';const nx=document.getElementById('next'),wf=document.getElementById('wantf');
function showNext(){if(nx&&nx.hidden){nx.hidden=false;ev('want_view')}}
nx&&nx.querySelectorAll('[data-want]').forEach(b=>b.onclick=()=>{
 WANT=b.dataset.want;nx.querySelectorAll('[data-want]').forEach(x=>x.classList.toggle('on',x===b));
 ev(WANT+'_click');wf.hidden=false;document.getElementById('wante').focus()});
wf&&(wf.onsubmit=async e=>{e.preventDefault();const fd=new FormData();
 fd.append('email',document.getElementById('wante').value);fd.append('reason','want:'+WANT);
 try{await fetch('/lead'+location.search,{method:'POST',body:fd})}catch(x){}
 ev('want_email',{why:WANT});wf.hidden=true;document.getElementById('wantok').hidden=false});
document.getElementById('navgo').onclick=x=>{x.preventDefault();ev('nav_cta');drop.scrollIntoView({behavior:'smooth',block:'center'});fi.click()};
document.getElementById('again').onclick=()=>{ev('again');drop.scrollIntoView({behavior:'smooth',block:'center'});fi.click()};
</script></body></html>"""
PAGE_HEAD = PAGE_HEAD.replace("__CFB__", CF_BEACON)


def _proof() -> dict:
    """Real output for the sample file, computed here, so the page cannot lie."""
    raw = _sample_pdf()
    doc = pymupdf.open(stream=raw, filetype="pdf")
    blocks = list(_blocks(doc))
    # ponytail: count printed lines, not blocks; "8 lines" from 2 pages reads as a toy
    printed = sum(len(b.get("lines", [])) for pg in doc
                  for b in pg.get_text("dict")["blocks"] if b.get("type") == 0)
    lines = ["".join(s["text"] for s in ln["spans"]).strip() for b in doc[0].get_text("dict")["blocks"]
             if b.get("type") == 0 for ln in b.get("lines", [])]
    chapters = _structure(blocks, doc)
    doc.close()
    paras = [t for ch in chapters for k, t in ch if k == "p"]
    heads = [t for ch in chapters for k, t in ch if k in ("h1", "h2")]
    # ponytail: the before/after shows page 1 twice, so the printed lines are the ones the
    # first two EPUB paragraphs were rebuilt from, and the header/page number are what got cut
    book = paras[:2]
    joined = " ".join(book)
    body = [ln for ln in lines if ln and ln not in heads and ln in joined]
    cut = [ln for ln in lines if ln and ln not in heads and ln not in joined and ln not in " ".join(paras)]
    return {
        "paras": printed,
        "eparas": len(paras),
        "toc": heads,
        "pdflines": body,
        "book": book,
        "runhead": cut[0] if cut else "",
        "pageno": cut[-1] if len(cut) > 1 else "",
    }


def _alternates(lang: str) -> str:
    # ponytail: hreflang tells google the three pages are one page in three languages, not duplicates
    path = {"en": "/"} | {k: f"/{k}/" for k in LANGS}
    links = [f'<link rel="canonical" href="https://epub.ftak.net{path[lang]}">']
    links += [f'<link rel="alternate" hreflang="{LANGS[k]["hreflang"] if k in LANGS else "en"}" '
              f'href="https://epub.ftak.net{u}">' for k, u in path.items()]
    links.append('<link rel="alternate" hreflang="x-default" href="https://epub.ftak.net/">')
    return "\n".join(links)


def _page(lang: str = "en") -> str:
    pr = _proof()
    pdflines = "".join(f'<div class="ln"><span>{html.escape(t)}</span><i aria-label="line break">&crarr;</i></div>'
                       for t in pr["pdflines"])
    bookparas = "".join(f"<p>{html.escape(t)}</p>" for t in pr["book"])
    faq = [(q.replace("__FREEOCR__", str(FREE_OCR_PAGES)), a.replace("__FREEOCR__", str(FREE_OCR_PAGES)))
           for q, a in FAQ.get(lang, FAQ["en"])]
    faq_html = "".join(f"<details><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>"
                       for q, a in faq)
    faq_ld = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
        ensure_ascii=False).replace("</", "<\\/")
    tpl = PAGE_HEAD
    for en, tr in (LANGS[lang]["pairs"] if lang in LANGS else []):
        assert en in tpl, f"{lang}: English text changed, update i18n.py: {en[:60]}"
        tpl = tpl.replace(en, tr)
    return (tpl
            .replace("__ALT__", _alternates(lang))
            .replace("__CSS__", PAGE_CSS)
            .replace("__PARAS__", str(pr["paras"]))
            .replace("__EPARAS__", str(pr["eparas"]))
            .replace("__TOCN__", str(len(pr["toc"])))
            .replace("__HEAD1__", html.escape(pr["toc"][0] if pr["toc"] else ""))
            .replace("__RUNHEAD__", html.escape(pr["runhead"]))
            .replace("__PAGENO__", html.escape(pr["pageno"]))
            .replace("__PDFLINES__", pdflines)
            .replace("__BOOKPARAS__", bookparas)
            .replace("__FAQLD__", faq_ld)
            .replace("__FAQ__", faq_html)
            .replace("__MAIL__", SHELF_MAIL)
            .replace("__TRACK__", TRACK_JS)
            .replace("__FREEOCR__", str(FREE_OCR_PAGES)))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    line = json.dumps({"t": datetime.now(timezone.utc).isoformat(), "visit": 1,
                       "ref": ref_of(request), "ua": ua_of(request)[:120]})
    _write(line)
    return _page()


@app.get("/pt/", response_class=HTMLResponse)
@app.get("/es/", response_class=HTMLResponse)
def index_lang(request: Request):
    lang = request.url.path.strip("/")
    _write(json.dumps({"t": datetime.now(timezone.utc).isoformat(), "visit": 1,
                       "ref": ref_of(request) or lang, "ua": ua_of(request)[:120]}))
    return _page(lang)

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
</style>__CFB__</head><body><div class="wrap">
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
 catch(e){msg.className='err';msg.innerHTML=failHtml(e);
  if(/^413/.test(e.message))msg.innerHTML=PITCH}
 go.disabled=false};
</script></body></html>"""
SCAN_PAGE = SCAN_PAGE.replace("__CFB__", CF_BEACON)


@app.get("/scan", response_class=HTMLResponse)
def scan_page():
    # ponytail: pitches link here, so it reports a view like the landing page does
    return SCAN_PAGE.replace("</body>", f"<script>{TRACK_JS}</script></body>", 1)


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
    tlang, elang = ocr_lang(doc)
    pics = {}
    pages = ocr_doc(doc, layout=True, lang=tlang, pics=pics) or []
    texts = [t for t, _ in pages]
    if not any(len(t) for t in texts):
        doc.close()
        log(False, npages, kb_in, 0, "scan-no-text", ref, request=request)
        raise HTTPException(422, "no readable text found, try a clearer photo of the page")
    figs = _scan_figures(doc, pages, pics)
    doc.close()
    data = build_epub(ocr_chapters(texts, figs), (title or "Scanned book")[:120], "", elang)
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
    title, desc, body, *rest = g
    return guide_page(title, desc, body, "/guides/" + slug, faq=rest[0] if rest else None,
                      h1=rest[1] if len(rest) > 1 else None)


# ponytail: IndexNow key is public by design, the file only proves we own the host
INDEXNOW_KEY = "ad136bf29681a09265f8e9bd56452473"


def site_urls() -> list[str]:
    return ["/", "/pt/", "/es/", "/scan", "/shelf", "/guides"] + ["/guides/" + s for s in GUIDES]


@app.get(f"/{INDEXNOW_KEY}.txt")
def indexnow_key():
    return Response(INDEXNOW_KEY, media_type="text/plain")


# Bing Webmaster Tools ownership file for epub.ftak.net
@app.get("/BingSiteAuth.xml")
def bing_site_auth():
    return Response('<?xml version="1.0"?>\n<users>\n\t<user>D3BEB7C7751AD491B57DB5CD64488E7A</user>\n</users>',
                    media_type="application/xml")


@app.get("/sitemap.xml")
def sitemap():
    urls = site_urls()
    body = "".join(f"<url><loc>https://epub.ftak.net{u}</loc></url>" for u in urls)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>',
                    media_type="application/xml")


def guide_page(title: str, desc: str, body: str, canonical: str, faq=None, h1=None) -> HTMLResponse:
    # ponytail: one template for every guide, no framework. faq = [(q, a)] -> visible list + FAQPage JSON-LD
    faq_html = faq_ld = ""
    if faq:
        faq_html = "<h2>FAQ</h2>" + "".join(f"<p><b>{html.escape(q)}</b><br>{html.escape(a)}</p>" for q, a in faq)
        faq_ld = '<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}) + "</script>"
    return HTMLResponse(f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/fonts.css">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="https://epub.ftak.net{canonical}">
{faq_ld}
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
</style>{CF_BEACON}</head><body><div class="wrap">
<a class="mark" href="/"><span class="dot"></span>pdf2epub</a>
<h1>{html.escape(h1 or title)}</h1>
{body}
{faq_html}
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
            "The first twenty pages of a scan are free. It is slower, because a machine is reading photographs of paper, but the output is the same EPUB with the same chapters and the same paragraphs.",
            "Nothing you upload is kept. The PDF is never saved, the EPUB is handed back as a download, and then it is gone. No account, no library, no copy on a disk somewhere waiting to be sold.",
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
    cid = re.sub(r"[^0-9A-Za-z_-]", "", request.query_params.get("checkout_id") or "")[:80]
    line = json.dumps({"t": datetime.now(timezone.utc).isoformat(), "visit": 1,
                       "ref": "thanks", "checkout_id": cid, "ua": ua_of(request)[:120]})
    _write(line)
    # ponytail: hand the subscriber their key here. polar sends the checkout id, so a junk request
    # gets no key. the key is what lifts the per-file ceiling, no account needed.
    key, batch = "", False
    if paid_checkout(cid, SHELF_PRODUCT):
        key = issue_key(cid)
    elif paid_checkout(cid, BATCH_PRODUCT):
        key, batch = issue_key(cid, BATCH_DAYS), True
    elif LIBRARY_PRODUCT and paid_checkout(cid, LIBRARY_PRODUCT):
        key, batch = issue_key(cid, LIBRARY_DAYS, LIBRARY_SHARP), True
    lib = bool(key) and sharp_left(key) > 0
    days = LIBRARY_DAYS if lib else BATCH_DAYS
    pname = "Library pass" if lib else ("Batch pass" if batch else "Shelf")
    key_html = ""
    if key:
        key_html = (f'<div class="card"><p><b>Your {pname} key</b></p>'
            f'<p>Put this on the end of the converter link and your uploads get the paid limits '
            f'(2,000 pages per file, 1GB){f" for the next {days} days. It does not renew" if batch else ""}. '
            f'This browser remembers it too:</p>'
            f'<p><code>https://epub.ftak.net/?k={key}</code></p>'
            f'<p>No account, no password. I also emailed it to the address you paid with, so it is '
            f'in your inbox for a new device. Not there in a few minutes? Check spam, or email '
            f'<code>{SHELF_MAIL}</code> and I will send it again.</p></div>')
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
<p>{f"The Library pass is {LIBRARY_DAYS} days of Shelf plus the sharper AI reading for faded scans, paid once" if lib else ("The Batch pass is 30 days of Shelf, paid once" if batch else "Shelf is $10 a month")}: no monthly limit,
any number of books, each up to 2,000 pages, scans included.</p>
{key_html}
<div class="card">
<p><b>What happens next</b></p>
<p>Your key is saved in this browser. Go to the <a href="/">converter</a> and upload: no monthly limit,
any number of books up to 2,000 pages each, scans get OCR (expect the usual OCR typos).</p>
<p>A file the converter chokes on? Email it to <code>{SHELF_MAIL}</code> with the book title in the subject line
and we will rerun it on the big-file converter.</p>
<p>Nothing is stored. The PDF is never saved and the EPUB is deleted after the download, same as the
<a href="/">free converter</a>.</p>
</div>
<p>Questions about the plan, or a file that is over 1GB? Same address.</p>
</div><script>{TRACK_JS}
ev('return',{{cid:{json.dumps(cid)}}});
if({json.dumps(key)})try{{localStorage.setItem('k',{json.dumps(key)})}}catch(e){{}}</script></body></html>""")


@app.get("/onebook", response_class=HTMLResponse)
def onebook(request: Request):
    # ponytail: separate polar success page for the $5 one-book unlock, so it never mints a Shelf key
    cid = re.sub(r"[^0-9A-Za-z_-]", "", request.query_params.get("checkout_id") or "")[:80]
    line = json.dumps({"t": datetime.now(timezone.utc).isoformat(), "visit": 1,
                       "ref": "onebook", "checkout_id": cid, "ua": ua_of(request)[:120]})
    _write(line)
    limit = onebook_pages(cid)
    paid = bool(limit)
    # ponytail: paid means the upload box right here, converted on the spot. email stays the fallback
    if paid:
        main = f"""<div class="card">
<p><b>Payment confirmed.</b> Choose the PDF and it converts now, up to {limit:,} pages, scans included.</p>
<input id="file" type="file" accept=".pdf">
<button class="btn" id="go">Convert my book</button>
<p id="msg"></p>
<p style="font-size:13px">One book per payment. Converting the same file again is free if you need to.
Bookmark this page: it is the only link to your purchase, there is no account.
A long scan takes a few minutes, keep this tab open.</p>
</div>
<p>Something wrong with the result? Email <code>{SHELF_MAIL}</code> with the checkout ID
<code>{html.escape(cid)}</code> and we will rerun it or refund you.</p>"""
    else:
        cid_html = (f"<p>Checkout ID: <code>{html.escape(cid)}</code></p>" if cid else
                    "<p>If you just paid and there is no checkout ID in the address, reply to the Polar receipt.</p>")
        main = f"""<div class="card">
<p><b>Payment not confirmed yet.</b> Polar can take a few seconds, so
<a href="">reload this page</a> first.</p>
<p>Still not confirmed? Reply to the Polar receipt or email <code>{SHELF_MAIL}</code> from the email you paid with,
and we will confirm the payment so this page unlocks the converter.</p>
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
<p>Paid once. Nothing is stored: the PDF is never saved and the EPUB is deleted after the download.</p>
{main}
<p><a href="/">Back to the free converter</a></p>
</div><script>{TRACK_JS}
ev('return',{{cid:{json.dumps(cid)}}});
if({json.dumps(paid)})try{{localStorage.setItem('onebook',{json.dumps(cid)})}}catch(e){{}}
const go=document.getElementById('go'),fi=document.getElementById('file'),msg=document.getElementById('msg');
if(go)go.onclick=async()=>{{
 const f=fi.files[0];if(!f){{msg.className='err';msg.textContent='Choose a PDF first.';return}}
 go.disabled=true;msg.className='';msg.textContent='Converting... a long scan takes a few minutes.';
 const fd=new FormData();fd.append('f',f);
 try{{const u=await runJob('/convert?paid='+encodeURIComponent({json.dumps(cid)}),fd,{{'X-V':V}},
   n=>{{msg.textContent='Still converting ('+clock(n)+'). Keep this tab open.'}});
  const a=document.createElement('a');a.href=u;
  a.download=(f.name||'book').replace(/\.pdf$/i,'')+'.epub';a.click();
  msg.className='ok';msg.textContent='Done. EPUB downloaded.';try{{localStorage.removeItem('onebook')}}catch(e){{}}}}
 catch(e){{msg.className='err';msg.innerHTML=failHtml(e)}}
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


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


@app.post("/freebook")
async def freebook(request: Request, email: str = Form(""), pages: int = Form(0)):
    # ponytail (11-12): sales came from talking to readers, and 102 cap hits left 6 emails. so the first whole
    # book is free for an email: they see the full book work, and we can write to them about the next one
    e = email.strip().lower()[:120]
    if not EMAIL_RE.match(e):
        return JSONResponse({"ok": False, "why": "email"}, status_code=400)
    rows = _freebook_rows()
    if any(len(r) > 1 and r[1] == e for r in rows if r[0] != "used"):
        return JSONResponse({"ok": False, "why": "used"}, status_code=409)
    ip = (request.client.host if request.client else "") or "-"
    today = datetime.now(timezone.utc).date().isoformat()
    if sum(1 for r in rows if r[0] != "used" and r[2:4] == [ip, today]) >= 2:
        return JSONResponse({"ok": False, "why": "used"}, status_code=429)
    token = secrets.token_urlsafe(12)
    try:
        with FREEBOOK.open("a") as fh:
            fh.write(f"{token} {e} {ip} {today}\n")
    except OSError:
        return JSONResponse({"ok": False}, status_code=500)
    _write(json.dumps({"t": datetime.now(timezone.utc).isoformat(), "ok": False, "pages": pages, "in": 0,
                       "out": 0, "err": "lead:freebook", "ref": ref_of(request), "email": e,
                       "ua": ua_of(request)[:120]}))
    return {"ok": True, "token": token}


LIBRARY_CARD = f"""<div class="card">
<p><b>A library of old scans? Library pass, $25 once</b></p>
<ul>
<li><b>{LIBRARY_DAYS} days</b> of the Shelf limits: any number of books, up to 2,000 pages each.</li>
<li><b>Sharper reading for faded print.</b> Regular OCR misreads old, faded or unusual type. Pages it is unsure of get a second reading by an AI vision model, up to {LIBRARY_SHARP:,} pages. On our test of faded Telugu pages, that took accuracy from 87% to 97%.</li>
<li>Telugu, Hindi, English, Portuguese and Spanish scans. No renewal.</li>
</ul>
<blockquote style="margin:14px 0 4px;padding:2px 0 2px 14px;border-left:3px solid var(--acc);color:var(--txt);font-family:var(--serif);font-size:17px;line-height:1.5">
"They look awesome. I never expected these weird formatted books could be converted to EPUB. Now I can read them on my phone and Kindle with font adjustments."</blockquote>
<p style="margin:0 0 6px;font-size:14px">A reader with a library of old Telugu books</p>
<a class="btn" href="/go/library?why=shelfpage" data-go>Library pass - $25 once</a>
</div>"""


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
<meta name="description" content="Shelf: $10/month, no monthly limit. Any number of books, each up to 2,000 pages, scans included.">
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
hit the free page cap. Shelf is for that reader.</p>
<div class="card">
<p><b>$10 a month, included</b></p>
<ul>
<li><b>No monthly limit.</b> Convert as many books as you like.</li>
<li><b>Big books go through.</b> The free converter stops at 150 pages, enough to try a book. Shelf takes up to 2,000 pages per file, scans included.</li>
<li>Repair: re-run and fix a conversion as many times as you want.</li>
<li>Nothing stored. The PDF is never saved and the EPUB is deleted after the download, same as the free tier.</li>
</ul>
<a class="btn" href="/go/shelf?why=shelfpage" data-go>Subscribe - $10/month</a>
<a class="btn" style="background:transparent;color:var(--txt);border:1px solid var(--line)" href="/go/batch?why=shelfpage" data-go>Or $10 once - 30 days, no renewal</a>
<p style="margin:12px 0 0;font-size:14px">One shelf to convert, not a habit? The one-time pass gives the same limits for 30 days and then simply ends. Not happy? Email me within 30 days of a payment and I refund it in full. Cancel any time.</p>
</div>
{LIBRARY_CARD if LIBRARY_URL and OPENROUTER_KEY else ""}
<p><b>What you get when you subscribe:</b> a private key. Put it on the end of
the converter link, like <code>epub.ftak.net/?k=YOURKEY</code>, and your uploads go to the paid
limits. No account, no password, nothing to set up.</p>
<div class="card">
<p><b>One big book, not a shelf?</b></p>
<p>Pay $5 once. You come straight back to an upload box and the book converts on the spot. Up to
2,000 pages. Scans get OCR.</p>
<a class="btn" href="/go/onebook?why=shelfpage" data-go>One book - $5</a>
<p style="margin:12px 0 0;font-size:14px">Not happy with the book? Full refund within 30 days, no questions asked.</p>
</div>
<p>Bigger than 2,000 pages? Still $5.
<a href="mailto:{SHELF_MAIL}?subject=Over%202000%20pages">Email us the page count</a>
and we raise the limit for your book.</p>
<p>The <a href="/">free converter</a> handles one PDF up to 1GB and 150 pages, and scans up to
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


@app.get("/llms.txt")
def llms_txt():
    # ponytail: AI assistants already send converters (chatgpt.com in /stats); give them the facts in one file
    guides = "\n".join(f"- [{v[0]}](https://epub.ftak.net/guides/{k})" for k, v in GUIDES.items())
    faq = "\n".join(f"- {q} {a}".replace("__FREEOCR__", str(FREE_OCR_PAGES)) for q, a in FAQ["en"])
    body = f"""# pdf2epub

> Free PDF to EPUB converter at https://epub.ftak.net. It rebuilds real paragraphs (not one line per printed line), turns headings into chapters with a clickable table of contents, drops running headers and page numbers, moves footnotes to the end of each chapter, and reads scanned books with OCR. Output is EPUB3 for Kindle (via Send to Kindle), Kobo, Apple Books and phone readers. No account, no watermark; PDFs are never saved and the EPUB is deleted after the download.

## Pricing

- Free: one PDF at a time, up to 150 pages and 1GB. Scanned books: the first {FREE_OCR_PAGES} pages get OCR free.
- One book: $5 once, up to 2,000 pages, scans included: https://epub.ftak.net/shelf
- Shelf: $10 a month, no monthly limit, any number of books up to 2,000 pages each, scans included: https://epub.ftak.net/shelf
- Batch pass: $10 once, the Shelf limits for 30 days, no renewal: https://epub.ftak.net/shelf

## Pages

- Converter (English): https://epub.ftak.net/
- Portuguese: https://epub.ftak.net/pt/
- Spanish: https://epub.ftak.net/es/
- Scan a physical book with your phone: https://epub.ftak.net/scan

## Guides

{guides}

## FAQ

{faq}
"""
    return Response(body, media_type="text/plain; charset=utf-8")


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
    return ("<h1>Privacy</h1><p>PDFs are never saved. The finished EPUB waits on the server until you download it (an hour at most), then it is deleted. Counts (pages, bytes) logged to conversions.log. "
            "If you type an email we keep it in the same log, used only to contact you about the paid tier and to email you a file "
            "if a conversion needs a queue. The page keeps a random id in your browser's localStorage so we can count "
            "how many people get from upload to download; it is not a cookie and is never linked to your name. "
            "No accounts, no third party analytics, nothing resold.</p><p><a href='/'>back</a></p>")

BEACONS = {"view", "multi_wall", "pick", "submit", "done", "fail", "pitch", "return", "sample", "lead", "faq", "again",
           "want_view", "translate_click", "desktop_click", "audio_click", "want_email", "djvu_pick", "kindle_click"}  # ponytail: want_* = fake doors; kindle (11-16): DropKind sells send-to-Kindle, new-Kindle wave from 11-28


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
    url = {"onebook": ONETIME_URL, "short": SHORT_URL, "shelf": SHELF_URL, "batch": BATCH_URL,
           "library": LIBRARY_URL if OPENROUTER_KEY else "",
           "translate": translate.TRANSLATE_URL}.get(offer)  # no model key = no AI reading to sell
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


def funnel_data(lines, days: int = 7, week: str = "") -> dict:
    """People per funnel step, by first-touch source. Joined on the page's random id `v`.

    ponytail (11-16): week=YYYY-MM-DD (a Monday, IST) gives that one week, for week-vs-week funnels."""
    since = datetime.now(timezone.utc).timestamp() - days * 86400
    until = float("inf")
    if week:
        start = datetime.fromisoformat(week + "T00:00:00+05:30")
        since, until = start.timestamp(), (start + timedelta(days=7)).timestamp()
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
        if t < since or t >= until:
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
    return {"days": days, "week": week or None, "rows": rows, "errors": dict(errs.most_common(12)),
            "server": {k: server[k] for k in ("visit", "converted", "wall", "click", "paid", "paid_convert")}}


@app.get("/funnel")
def funnel(request: Request):
    if not FUNNEL_KEY or request.query_params.get("k") != FUNNEL_KEY:
        raise HTTPException(404, "Not Found")
    try:
        days = max(1, min(90, int(request.query_params.get("days") or 7)))
    except ValueError:
        days = 7
    week = request.query_params.get("week") or ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", week):
        week = ""
    lines = []
    for f in (LOG.with_suffix(".log.1"), LOG):
        try:
            lines += f.read_text().splitlines()
        except OSError:
            pass
    d = funnel_data(lines, days, week)
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
def stats(response: Response):
    # ponytail: totals from log file, no DB/dashboard lib. noindex: GSC listed /stats as a crawled page (11-10)
    response.headers["X-Robots-Tag"] = "noindex"
    ok = fail = pages = visits = ocr = scan_fail = emails = 0
    emailset = set()
    leads = cap_rejects = checkouts = 0
    refs: dict[str, int] = {}
    ok_by_ref: dict[str, int] = {}
    uas: dict[str, int] = {}
    visits_bot = visits_human = visits_unknown = 0
    conv_bot = conv_human = 0
    fail_by_err: dict[str, int] = {}
    recent_fails: list[dict] = []
    starts = 0
    weekly: dict[str, dict[str, int]] = {}  # ponytail (11-16): user wanted week-vs-week, not all-time totals

    def wk(r) -> dict[str, int]:
        # Monday-start week in IST (the user's clock); bad or missing t lands in "?"
        try:
            d = (datetime.fromisoformat(r.get("t", "")) + timedelta(hours=5, minutes=30)).date()
            k = (d - timedelta(days=d.weekday())).isoformat()
        except (ValueError, TypeError):
            k = "?"
        return weekly.setdefault(k, {"visits_human": 0, "conversions_human": 0, "cap_rejects": 0,
                                     "checkouts": 0, "leads": 0})
    suspect = {}  # books whose structure looks broken (_suspect), by reason
    wants = {"want_view": 0, "translate_click": 0, "desktop_click": 0, "audio_click": 0, "want_email": 0, "djvu_pick": 0, "kindle_click": 0}
    try:
        for line in LOG.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("ev"):
                starts += r["ev"] == "start"
                if r["ev"] == "suspect" and not is_bot(r.get("ua") or ""):
                    suspect[r.get("why") or "?"] = suspect.get(r.get("why") or "?", 0) + 1
                if r["ev"] in wants and not is_bot(r.get("ua") or ""):
                    wants[r["ev"]] += 1  # ponytail: starts minus outcomes = workers killed mid-book
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
                    wk(r)["visits_human"] += 1
                if r.get("checkout_id"):
                    wk(r)["checkouts"] += 1
                short = ua.split(")")[-1].strip()[:48] if ua else "(no user agent)"
                uas[short] = uas.get(short, 0) + 1
                continue
            ok += bool(r.get("ok"))
            fail += not r.get("ok")
            pages += int(r.get("pages", 0))
            c = r.get("err", "")
            ocr += bool(r.get("ok")) and c == "ocr"
            scan_fail += (not r.get("ok")) and c.startswith("scan")
            if r.get("email"):  # ponytail: one person can leave the same email on several lines
                emailset.add(r["email"].strip().lower())
            if not r.get("ok") and ua and not is_bot(ua) and not c.startswith("lead"):
                kind = c.split(":")[0] if c.startswith("crash") else (c or "?")
                fail_by_err[kind] = fail_by_err.get(kind, 0) + 1
                recent_fails.append({"t": r.get("t", "")[:16], "err": c, "pages": r.get("pages", 0),
                                     "kb": r.get("in", 0), "src": (r.get("ref") or "direct").split("|")[0] or "direct"})
            leads += 1 if c.startswith("lead") else 0
            cap_rejects += 1 if c in ("too many pages", "too big") else 0
            if c.startswith("lead"):
                wk(r)["leads"] += 1
            if c in ("too many pages", "too big") and not is_bot(ua):
                wk(r)["cap_rejects"] += 1
            if r.get("ok"):  # ponytail: per-launch-post measurement, ref tag before the pipe
                key = (r.get("ref") or "direct").split("|")[0] or "direct"
                ok_by_ref[key] = ok_by_ref.get(key, 0) + 1
                if is_bot(ua):
                    conv_bot += 1
                else:
                    conv_human += 1
                    wk(r)["conversions_human"] += 1
    except OSError:
        pass
    top = dict(sorted(refs.items(), key=lambda kv: -kv[1])[:10])
    top_ok = dict(sorted(ok_by_ref.items(), key=lambda kv: -kv[1])[:10])
    return {"visits": visits, "refs": top, "conversions_ok": ok, "ocr_ok": ocr,
            "failed": fail, "scan_fail": scan_fail, "pages": pages, "ok_by_ref": top_ok,
            "emails_captured": len(emailset), "leads": leads, "cap_rejects": cap_rejects,
            "checkouts": checkouts,
            "visits_human": visits_human, "visits_bot": visits_bot,
            "visits_unknown": visits_unknown,
            "conversions_human": conv_human, "conversions_bot": conv_bot,
            "starts": starts, "wants": wants, "suspect": suspect, "fail_by_err": dict(sorted(fail_by_err.items(), key=lambda kv: -kv[1])),
            "recent_fails": recent_fails[-15:],
            "user_agents": dict(sorted(uas.items(), key=lambda kv: -kv[1])[:8]),
            "weekly": dict(sorted(kv for kv in weekly.items() if kv[0] != "?")[-12:])}

def _join(lines):
    """Join the wrapped lines of one paragraph; drop the hyphen at a line break."""
    out = ""
    for ln in lines:
        if not out:
            out = ln
        elif out.endswith("​"):  # publishers break long URLs at a zero-width space
            out = out[:-1] + ln
        elif out.endswith("-"):
            out = out[:-1] + ln
        else:
            out += " " + ln
    return re.sub(r"\s+", " ", out.replace("​", "")).strip()


SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")

LIGS = ("ffi", "ffl", "ff", "fi", "fl")
LIG_SAFE = set("'’‘-‐‑–—./&@_:")  # legit inside a word ("don't", "and/or", "e.g.")


def _lig_keys():
    # "<2 before>|lig|<2 after>" windows from dictionary words with fi/ff/fl; ^ $ mark word edges.
    # 2 letters of context, not the whole word, so "offered" matches via "offer".
    keys = set()
    try:
        words = (Path(__file__).parent / "ligwords.txt").read_text().split()
    except OSError:
        return keys
    for w in words:
        for lig in LIGS:
            for m in re.finditer(f"(?={lig})", w):
                i, j = m.start(), m.start() + len(lig)
                keys.add(("^" if i < 2 else "") + w[max(0, i - 2):i] + "|" + lig + "|"
                         + w[j:j + 2] + ("$" if j + 2 > len(w) else ""))
    return keys


LIG_KEYS = _lig_keys()
try:
    LIG_WORDS = set((Path(__file__).parent / "ligwords.txt").read_text().split())
except OSError:
    LIG_WORDS = set()


def _lig_map(doc):
    """{font: {bad_char: ligature}} for fonts whose ToUnicode map sends ligature glyphs to junk.

    ponytail: the first paying buyer's book read "fi" as "Dž" and "ff" as "!" ("stu!.",
    "Džnger"). The glyph is right, so the PDF looks fine; only its text layer is wrong. Each
    suspect char in each font votes: a ligature wins when the letters around it spell dictionary
    words. A real "Wow!" never spells one, so it stays.
    """
    votes, seen = {}, Counter()
    for page in doc:
        for b in page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
            for line in b.get("lines", []):
                # context comes from the whole line: Kindle exports put the ligature glyph in a
                # span of its own ("di" | "ǃerent"), so per span every hit looks like a word start.
                t = "".join(sp["text"] for sp in line["spans"])
                fonts = [sp["font"] for sp in line["spans"] for _ in sp["text"]]
                for k, ch in enumerate(t):
                    if ch.isspace() or ch in LIG_SAFE or (ch.isascii() and ch.isalnum()):
                        continue
                    if ch.isalpha() and not 0x180 <= ord(ch) <= 0x24F and ord(ch) < 0xE000:
                        continue  # real accented letters stay; Latin Extended-B (Dž, ǃ, Ǐ) and private use are suspects
                    l = re.search(r"[A-Za-z]{0,2}$", t[:k]).group().lower()
                    r = re.match(r"[A-Za-z]{0,2}", t[k + 1:]).group().lower()
                    if not l and not r:
                        continue
                    if not (l and r) and not ch.isalpha():
                        continue  # punctuation votes mid-word only: "(th" spells "fifth", "o!ce" can't be a real "!"
                    f = fonts[k]
                    seen[f, ch] += 1
                    for lig in LIGS:
                        key = (("^" if len(l) < 2 else "") + l + "|" + lig + "|" + r
                               + ("$" if len(r) < 2 else ""))
                        if key in LIG_KEYS:
                            votes.setdefault((f, ch), Counter())[lig] += 1
    out = {}
    for (f, ch), c in votes.items():
        lig, n = c.most_common(1)[0]
        if n >= 3 and n >= seen[f, ch] * 0.6:
            out.setdefault(f, {})[ch] = lig
    # a stray letter with too few hits in its own font ("scotthunteroǏcial" in bold) borrows
    # the ligature that letter means in a sibling font of the same family (Bookerly-Regular)
    for f, ch in seen:
        if ch.isalpha() and ch not in out.get(f, {}):
            fam = f.split("-")[0]
            sib = Counter(m[ch] for g, m in out.items() if g.split("-")[0] == fam and ch in m)
            if sib:
                out.setdefault(f, {})[ch] = sib.most_common(1)[0][0]
    return out


def _lig_ok(t, k, lig):
    # a stray letter (Dž, private use) is always the ligature. Punctuation like "!" can be both
    # the broken ff and a real "Wow!" in the same font, so swap it only between letters or where
    # the letters around it spell a word ("stu!." -> "stuff.").
    ch = t[k]
    if ch.isalpha():
        return True
    l = re.search(r"[A-Za-z]{0,2}$", t[:k]).group().lower()
    r = re.match(r"[A-Za-z]{0,2}", t[k + 1:]).group().lower()
    if l and r:
        return True
    if not r:  # word end: "stu!" -> "stuff" is a word, "Wow!" -> "wowff" is not
        return re.search(r"[A-Za-z]*$", t[:k]).group().lower() + lig in LIG_WORDS
    return (("^" if len(l) < 2 else "") + l + "|" + lig + "|" + r + ("$" if len(r) < 2 else "")) in LIG_KEYS


PRESENTATION_LIGS = str.maketrans({"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl"})


def _fix_line(line, ligmap):
    # real ligature chars (U+FB01 "ﬁ") break search and fonts without the glyph: plain letters
    for sp in line["spans"]:
        sp["text"] = sp["text"].translate(PRESENTATION_LIGS)
    if not ligmap or not any(sp["font"] in ligmap for sp in line["spans"]):
        return
    t = "".join(sp["text"] for sp in line["spans"])
    k = 0
    for sp in line["spans"]:
        m, old = ligmap.get(sp["font"]), sp["text"]
        if m:
            sp["text"] = "".join(m[ch] if ch in m and _lig_ok(t, k + j, m[ch]) else ch
                                 for j, ch in enumerate(old))
        k += len(old)


SPACED_LINE = re.compile(r"(?:\b\w ){4,}\w\b")


def _unspace(page, line):
    """Letter-spaced type ("T h e  C h a i n", Paramattha captions 11-21) comes out with a space between
    every letter. Re-read the line's characters: a space under 0.2 em wide is tracking, a real word
    space is wider (0.21-0.3 em), so dropping the narrow ones gives the words back."""
    t = "".join(sp["text"] for sp in line["spans"])
    if not SPACED_LINE.search(t) or len(re.findall(r"\b\w\b", t)) < 0.4 * len(t.split()):
        return
    out = []
    for b in page.get_text("rawdict", clip=pymupdf.Rect(line["bbox"]) + (-1, -1, 1, 1))["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                for c in sp["chars"]:
                    if c["c"] == " " and c["bbox"][2] - c["bbox"][0] < 0.2 * sp["size"]:
                        continue
                    out.append(c["c"])
            out.append(" ")
    fixed = re.sub(r"\s+", " ", "".join(out)).strip()
    if fixed and len(fixed) < len(t.strip()):
        line["spans"][0]["text"] = fixed
        for sp in line["spans"][1:]:
            sp["text"] = ""


def _span_text(s):
    # ponytail: flattening spans loses the superscript flag, so a footnote marker reads as a
    # normal digit glued to the sentence ("argument.12"). unicode keeps it visibly raised.
    t = s["text"]
    # in a math font a raised or lowered digit is an index (b44, P3,1), not a note marker
    if s["flags"] & 1 and t.strip().isdigit() and len(t.strip()) <= 3 and not MATH_FONT.search(s.get("font", "")):
        return t.translate(SUP)
    return t


# Math in papers. ponytail (11-19 lead, two papers "did not convert well"): a display equation
# is a 2D layout (fractions, sums, sub- and superscripts) that text can't hold, and old journal
# PDFs draw their symbols with private "Pi" fonts whose letters mean other glyphs.
MATH_FONT = re.compile(r"Math|Pi\b|Pi-|Sym|CMMI|CMSY|CMEX|MSAM|MSBM|MTMI|MTSY|MTEX|Euclid|rsfs", re.I)
# 1990s Elsevier (Acrobat Distiller) Pi fonts: Times letters stand for the math glyphs.
# Read off a 1999 Wear paper: "zs0" is z=0, "Ž i, j ." is (i, j), "´" is epsilon.
PI_MAPS = {
    "SizedSym": str.maketrans({"Ž": "(", ".": ")", "ž": "(", "/": ")", "Ý": "Σ", "Ł": "Π", "H": "∫"}),
    "ScienceTypeCustomPi-No5T": str.maketrans({"y": "−", "s": "=", "w": "[", "x": "]", "q": "+",
                                               "r": "/", "g": "∈", "f": "∉", "F": "≤", "G": "≥"}),
    "ScienceTypeCustomPi-No4T": str.maketrans({")": "*", "f": "∉"}),
    "ScienceTypeCustomPi-No3T": str.maketrans({"=": "×", "<": "|", "X": "′", "-": "<", ")": ">",
                                               "/": "≠", ";": "≈", "'": "≡"}),
    "ScienceTypeCustomPi-No2T": str.maketrans({"§": "←"}),
    "MathematicalPi-One": str.maketrans({"´": "ε", "a": "α", "b": "β", "d": "δ", "m": "μ", "n": "ν",
                                         "p": "π", "s": "σ", "t": "τ", ";": "∀"}),
    "ElsevierSpecialPi": str.maketrans({"Õ": "v"}),
    "Universal-NewswithCommPi": str.maketrans({"q": "©", "B": "∅"}),
}
# LaTeX papers built with a wrong input encoding: UTF-8 quote bytes read as another code page
MOJIBAKE = (("âĂŹ", "’"), ("âĂĲ", "“"), ("âĂİ", "”"), ("âĂŞ", "–"), ("âĂŤ", "—"), ("âĂŸ", "‘"))


def _math_char(ch: str) -> str:
    # ponytail: STIX/Cambria math italics live at U+1D4xx; some PDF text layers drop the top bit,
    # so "x" came out as Korean "푥" (U+D465). Put the bit back and take the plain letter.
    o = ord(ch)
    if 0xD400 <= o <= 0xD7FF:
        return unicodedata.normalize("NFKC", chr(o + 0x10000))
    return unicodedata.normalize("NFKC", ch) if 0x1D400 <= o <= 0x1D7FF else ch


def _fix_math_span(sp):
    f = sp["font"]
    pi = next((m for k, m in PI_MAPS.items() if f.split("+")[-1].startswith(k)), None)
    if pi:
        sp["text"] = sp["text"].translate(pi)
    elif MATH_FONT.search(f):
        sp["text"] = "".join(_math_char(c) for c in sp["text"])
    if "âĂ" in sp["text"]:
        for a, b in MOJIBAKE:
            sp["text"] = sp["text"].replace(a, b)


def _merge_bands(b):
    """Lines of one visual line, rebuilt in x order, for blocks that hold math.

    ponytail: a Distiller paper put each big parenthesis and each subscript on a PDF line of its
    own, so "(i, j)" came out as "Ž / . / i, j" with the brackets a line above the words.
    """
    lines = b.get("lines", [])
    if len(lines) < 2 or not any(MATH_FONT.search(s["font"]) for ln in lines for s in ln["spans"]):
        return
    bands = []
    for ln in sorted(lines, key=lambda l: l["bbox"][1]):
        x0, y0, x1, y1 = ln["bbox"]
        h, cy = max(y1 - y0, 0.1), (y0 + y1) / 2
        for bd in bands:
            by0, by1 = bd["bbox"][1], bd["bbox"][3]
            bh = max(by1 - by0, 0.1)
            if by0 <= cy <= by1 and max(h, bh) / min(h, bh) <= 2.2:
                bd["parts"].append(ln)
                bd["bbox"] = [min(bd["bbox"][0], x0), min(by0, y0), max(bd["bbox"][2], x1), max(by1, y1)]
                break
        else:
            bands.append({"parts": [ln], "bbox": [x0, y0, x1, y1]})
    out = []
    for bd in bands:
        spans = sorted((s for ln in bd["parts"] for s in ln["spans"]), key=lambda s: s["bbox"][0])
        merged, last_x1 = [], None
        for s in spans:
            if last_x1 is not None and s["bbox"][0] - last_x1 > s["size"] * 0.2 \
                    and merged and not merged[-1]["text"].endswith((" ", "(", "[", "{")) \
                    and not s["text"].startswith((" ", ")", "]", "}", ",", ".", ";", ":")):
                merged.append({**s, "text": " "})
            merged.append(s)
            last_x1 = max(last_x1 or s["bbox"][2], s["bbox"][2])
        out.append({**bd["parts"][0], "spans": merged, "bbox": tuple(bd["bbox"])})
    b["lines"] = out


def _line_size(line):
    # a big bracket or sum sign drawn in a math font is not a heading-sized line
    sizes = [s["size"] for s in line["spans"] if s["text"].strip() and not MATH_FONT.search(s["font"])]
    return max(sizes or [s["size"] for s in line["spans"]])


def _eq_image(page, r, body):
    """(picture, "", width in em): sized in the book to match the text around it."""
    clip = (r + (-2, -2, 2, 2)) & page.rect
    pm = page.get_pixmap(matrix=pymupdf.Matrix(EQ_SCALE, EQ_SCALE), clip=clip)
    return _fig_bytes(pm), "", round(clip.width / max(body, 1), 1)


EQ_NO = re.compile(r"^\(\d{1,3}[a-z]?\)$")
PROSE_WORD = re.compile(r"[A-Za-z]{3,}")
MATH_NAMES = {"sin", "cos", "tan", "exp", "log", "sinh", "cosh", "tanh", "max", "min", "lim", "det", "arg"}
MATH_SYM = set("=≤≥<>∑∫Σ∏√∂∇±×≈+−←∈∉≠≡")
EQ_SCALE = 3


def _equations(raw, page_h):
    """Display equations on a page: [(rect, {block index, ...}), ...].

    A block is an equation when its text is mostly not words and it draws math (a math font or
    an "="); touching blocks join it (LaTeX writes one equation as a dozen small blocks), so do
    a short leftover like a subscript and the "(12)" number at the right margin. A math block
    that sits on a prose line is inline math and stays text.
    """
    info = {}
    for k, b in enumerate(raw):
        if b.get("type") != 0 or b["bbox"][1] < 50 or b["bbox"][3] > page_h - 50:
            continue
        spans = [s for ln in b.get("lines", []) for s in ln["spans"]]
        chars = sum(len(s["text"].replace(" ", "")) for s in spans)
        if not chars:
            continue
        prose = sum(len(w) for s in spans if not MATH_FONT.search(s["font"])
                    for w in PROSE_WORD.findall(s["text"]) if w.lower() not in MATH_NAMES)
        mathy = sum(len(s["text"].strip()) for s in spans if MATH_FONT.search(s["font"]))
        text = "".join(s["text"] for s in spans).strip()
        info[k] = (prose, chars, mathy, text)
    # a prose line with a bracket in a Pi font ("was made in Ref. [3]") is not an equation: it
    # needs a relation or an operator, or nothing but math type
    seeds = {k for k, (prose, chars, mathy, text) in info.items()
             if prose < chars * 0.25 and prose < 12 and not EQ_NO.match(text)
             and (MATH_SYM & set(text) or (mathy >= 2 and prose == 0))}
    prose_rects = [pymupdf.Rect(raw[k]["bbox"]) for k, (prose, *_) in info.items() if k not in seeds and prose >= 12]

    def inline(r):
        return any(min(r.y1, p.y1) - max(r.y0, p.y0) > 0.3 * min(r.height, p.height)
                   and min(r.x1, p.x1) - max(r.x0, p.x0) > -6 for p in prose_rects)

    clusters = []
    for k in sorted(seeds, key=lambda k: raw[k]["bbox"][1]):
        r = pymupdf.Rect(raw[k]["bbox"])
        for c in clusters:
            if (c[0] + (-4, -4, 4, 4)).intersects(r):
                c[0] |= r
                c[1].add(k)
                break
        else:
            clusters.append([r, {k}])
    _merge_touching(clusters)
    out = []
    for r, ks in clusters:
        if inline(r):
            continue
        grew = True
        while grew:  # subscripts, limits and the equation number
            grew = False
            for k, (prose, chars, mathy, text) in info.items():
                if k in ks or k in seeds:
                    continue
                kr = pymupdf.Rect(raw[k]["bbox"])
                small = prose == 0 and chars <= 12
                number = EQ_NO.match(text) and min(kr.y1, r.y1) - max(kr.y0, r.y0) > 0
                if (small and (r + (-4, -4, 4, 4)).intersects(kr)) or number:
                    r |= kr
                    ks.add(k)
                    grew = True
        out.append([r, ks])
    _merge_touching(out)  # a piece grown into one cluster can touch another
    return [(r, ks) for r, ks in out]


def _merge_touching(clusters):
    """Join [rect, keys] clusters that touch, in place: one equation drawn as side-by-side parts."""
    merged = True
    while merged:
        merged = False
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                if (clusters[a][0] + (-4, -4, 4, 4)).intersects(clusters[b][0]):
                    clusters[a][0] |= clusters[b][0]
                    clusters[a][1] |= clusters[b][1]
                    del clusters[b]
                    merged = True
                    break
            if merged:
                break


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
    if _body_chars_in(u, blocks, body) >= 80:
        return None
    return _with_labels(u, blocks) & page.mediabox


def _with_labels(u, blocks):
    # ponytail: sub-captions ("(a) Analytical and numerical ...") are centred under each panel
    # and run wider than the plot, so the clip cut their first letters off (11-19 lead's paper)
    for b in blocks:
        if b.get("type") != 0:
            continue
        r = pymupdf.Rect(b["bbox"])
        if u.contains(pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)):
            u = u | r
    return u


def _body_chars_in(u, blocks, body) -> int:
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
    return body_chars


def _figure_rects(page, blocks, body, small: bool = False) -> list:
    """Clip rects of the figures on a page, top first.

    ponytail: a journal page with two figures and prose between them (1999 paper, figs 2-5)
    failed the one-box test, since the union held the prose, and both figures were dropped.
    Then each embedded picture is its own figure.
    """
    u = _figure_rect(page, blocks, body)
    if u:
        return [u]
    area = page.rect.width * page.rect.height
    out = []
    # ponytail: born-digital books place small pictures on purpose: Paramattha's 51pt section icons
    # (11-21) were under the 3%-of-page floor and 73 of 155 pictures went missing. Scans keep the floor,
    # their small "pictures" are specks and stamps.
    big_enough = (lambda r: r.width >= 20 and r.height >= 20) if small else \
        (lambda r: (r.width * r.height) / area > 0.03)
    for info in page.get_image_info():
        r = pymupdf.Rect(info["bbox"]) & page.mediabox
        if not big_enough(r) or (r.width * r.height) / area > 0.8 or _body_chars_in(r, blocks, body) >= 80:
            continue
        if any(o.contains(r) for o in out):
            continue
        # a picture stacked on another (a tint or frame over a photo) is one figure, rendered together
        over = [o for o in out if not (o & r).is_empty and (o & r).get_area() > 0.5 * min(o.get_area(), r.get_area())]
        for o in over:
            r = r | o
        out = [o for o in out if o not in over and not r.contains(o)] + [_with_labels(r, blocks) & page.mediabox]
    if small:
        return sorted(out, key=lambda r: (r.y0, r.x0))
    return sorted(out, key=lambda r: (r.y0, r.x0)) if len(out) > 1 else []


def _table_rects(page, raw, body, eqs=()) -> list:
    """Areas of a born-digital page laid out as a table: rows of two or more short cells side by side.

    ponytail: Paramattha's emotion tables and 12-links chart (11-21) came out as one cell per line
    ("Mental Life / Agitation / Unpleasant Feeling") with the rows' order lost. Text can't keep a
    table's grid, a picture of that area can. Two-column prose (papers) has long lines, so the
    short-cell test leaves it alone; a numbered list that continues in the second column is a list.
    """
    lines = []
    for b in raw:
        for ln in b.get("lines", []):
            t = "".join(sp["text"] for sp in ln["spans"]).strip()
            if t:
                lines.append((pymupdf.Rect(ln["bbox"]), t, max(sp["size"] for sp in ln["spans"])))
    rows = []
    for r, t, sz in sorted(lines, key=lambda x: (x[0].y0, x[0].x0)):
        if rows and abs(rows[-1][0][0].y0 - r.y0) < 3:
            rows[-1].append((r, t, sz))
        else:
            rows.append([(r, t, sz)])
    paired = []
    for row in rows:
        row.sort(key=lambda x: x[0].x0)
        if any(b[0].x0 - a[0].x1 > 25 for a, b in zip(row, row[1:])):
            paired.append(row)
    out, band = [], []
    for row in paired + [None]:
        if row and (not band or row[0][0].y0 - band[-1][0][0].y1 < 40):
            band.append(row)
            continue
        if len(band) >= 4:
            cells = [c for rw in band for c in rw]
            u = pymupdf.Rect(cells[0][0])
            for c in cells[1:]:
                u |= c[0]
            # wrapped single-cell lines between the paired rows belong to the table too
            for r, t, sz in lines:
                if u.y0 - 2 <= r.y0 <= u.y1 + 2 and r.x0 >= u.x0 - 5:
                    u |= r
            lens = sorted(len(c[1]) for c in cells)
            col_med = lambda side: sorted(len(rw[side][1]) for rw in band)[len(band) // 2]
            # an equation and its "(3)" number sit side by side too; papers' abstract boxes pair a short
            # "ARTICLE INFO" column with long abstract lines (cas-sc-template, 11-21): neither is a table
            eq_nums = sum(bool(re.fullmatch(r"\(\s*\d{1,3}[a-z]?\s*\)", rw[-1][1])) for rw in band)
            if eq_nums >= len(band) * 0.3 or col_med(0) >= 40 or col_med(-1) >= 40 \
                    or any(not (u & e).is_empty for e in eqs) \
                    or any(MATH_FONT.search(sp.get("font", "")) for b in raw for ln in b.get("lines", [])
                           for sp in ln["spans"] if u.contains(pymupdf.Rect(ln["bbox"]))):
                band = [row] if row else []
                continue
            nums = lambda side: [int(m.group(1)) for rw in band for m in [re.match(r"\(?(\d{1,3})[).]", rw[side][1])] if m]
            left, right = nums(0), nums(-1)
            seq_list = left and right and min(right) > max(left)
            small = sum(c[2] < body * 1.05 for c in cells) >= len(cells) * 0.6
            if lens[len(lens) // 2] < 40 and u.height < page.rect.height * 0.7 and not seq_list and small:
                for info in page.get_image_info():
                    ir = pymupdf.Rect(info["bbox"])
                    if ir.y1 > u.y0 and ir.y0 < u.y1:
                        u |= ir
                out.append((u + (-4, -4, 4, 4)) & page.mediabox)
        band = [row] if row else []
    return out


def _fig_caption(page, raw, fig_page):
    """(caption, its rect on the page) under a figure, or ("", None).

    Put a "Map 4.1 ..." caption under its picture. PDF block order is not y-sorted,
    so without this the caption can land a paragraph after the map. Captions on
    landscape pages sit beside the figure in PDF space, so compare on the page.
    """
    cap, cap_page = "", None
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
            # ponytail: a journal caption runs on in blocks of its own under the first
            # line; they were glued into the body paragraph before the figure (1999 paper)
            csize = max((sp["size"] for ln in cb.get("lines", []) for sp in ln["spans"]), default=0)
            more = True
            while more:
                more = False
                for nb in raw:
                    if nb.get("type") != 0 or nb is cb:
                        continue
                    nr = _page_rect(page, pymupdf.Rect(nb["bbox"]))
                    nsize = max((sp["size"] for ln in nb.get("lines", []) for sp in ln["spans"]), default=99)
                    ntxt = _join(["".join(_span_text(sp) for sp in ln["spans"]).strip()
                                  for ln in nb.get("lines", [])])
                    if (cap_page.y1 - 2 <= nr.y0 <= cap_page.y1 + csize * 0.8 and nsize <= csize + 0.3
                            and min(nr.x1, cap_page.x1) - max(nr.x0, cap_page.x0) > 0
                            and ntxt and not CAPTION_RE.match(ntxt)):
                        cap, cap_page = _join([cap, ntxt]), cap_page | nr
                        more = True
                        break
            break
    return cap, cap_page


PHOTO_CELL = 4  # px at 36 dpi, about one printed line tall


def _wordy_line(t: str, known: Counter) -> bool:
    ws = WORD3.findall(t)
    return bool(ws) and sum(known[w.lower()] >= 3 for w in ws) >= 0.6 * len(ws)


def _text_cover(raw, r) -> float:
    """Share of a region covered by OCR line boxes (any text, junk included)."""
    area = r.width * r.height or 1
    return sum((pymupdf.Rect(ln["bbox"]) & r).get_area() for b in raw for ln in b.get("lines", [])
               if "".join(s["text"] for s in ln["spans"]).strip()) / area


def _lined(g, dark: int) -> bool:
    """Printed lines leave blank pixel rows between them; a picture has almost none."""
    w, px = g.width, g.tobytes()
    blank = sum(1 for y in range(g.height) if sum(v < dark for v in px[y * w:(y + 1) * w]) < 0.01 * w)
    return blank >= 0.2 * g.height


def _pctl(hist, q):
    total, acc = sum(hist), 0
    for v, n in enumerate(hist):
        acc += n
        if acc >= q * total:
            return v
    return 255


def _scan_background(page):
    """The picture layer of a two-layer page scan, as a PIL RGB image, else None.

    Internet Archive and LuraDocument scans store a page as a low-res background (paper, photos,
    drawings, tints) under a masked high-res layer that carries only the letters. Pictures found
    on the background alone are not confused with print, and it decodes 5x faster than the page.
    """
    from PIL import Image
    area = page.rect.get_area()
    full = []  # (xref, smask) of images covering the page; get_image_info would decode them all
    for it in page.get_images(full=True):
        try:
            if (page.get_image_bbox(it) & page.rect).get_area() >= 0.95 * area:
                full.append((it[0], it[1]))
        except Exception:
            continue
    bg = [x for x, m in full if not m]
    if len(full) < 2 or len(bg) != 1 or not any(m for _, m in full):
        return None
    try:
        pix = pymupdf.Pixmap(page.parent, bg[0])
        if pix.alpha:
            pix = pymupdf.Pixmap(pix, 0)
        if pix.n != 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    except Exception:
        return None


def _scan_photos(page, raw, known: Counter) -> list:
    """Picture regions on a page scan that carries an OCR layer, as page rects.

    ponytail: an OCR-layer page is one page-sized image, so _figure_rect skips it and every picture
    in the book was dropped: a 260-page posture book came out with 15, the cover and junk pages
    (reddit 11-18, Spiritual-Willow2778; convert2epub drops them too). Mark what is not paper (dark,
    or more colourful than the paper), white out the lines OCR read as real words, join what is
    left into regions; a region mostly covered by OCR lines is print, the rest are pictures. Colour
    matters: thin light anatomy drawings and people cut out on white have little dark ink.
    """
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat
    rgb = _scan_background(page)
    layered = rgb is not None
    if rgb is None:
        pm = page.get_pixmap(matrix=pymupdf.Matrix(1, 1), colorspace=pymupdf.csRGB, alpha=False)
        rgb = Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
    f = rgb.width / page.rect.width  # image pixels per point
    lum, sat = rgb.convert("L"), rgb.convert("HSV").split()[1]
    paper, paper_sat = _pctl(lum.histogram(), 0.9), _pctl(sat.histogram(), 0.5)
    lum_cut, sat_cut = int(paper * 0.88), min(250, paper_sat + 35)
    mask = ImageChops.lighter(lum.point(lambda v: 255 if v < lum_cut else 0),
                              sat.point(lambda v: 255 if v > sat_cut else 0))
    dr = ImageDraw.Draw(mask)
    for b in raw:
        for ln in b.get("lines", []):
            if _wordy_line("".join(s["text"] for s in ln["spans"]), known):
                x0, y0, x1, y1 = ln["bbox"]
                dr.rectangle([x0 * f - 2, y0 * f - 2, x1 * f + 2, y1 * f + 2], fill=0)
    C = max(4, round(8 * f))  # about 8pt
    W, H = mask.width // C, mask.height // C
    if not W or not H:
        return []
    # share of marked pixels per cell, then grow so a figure's parts join up
    cells = mask.crop((0, 0, W * C, H * C)).resize((W, H), Image.BOX).point(lambda v: 255 if v >= 255 * 0.04 else 0)
    px = cells.tobytes()

    def comps(grow, inside=None):
        gx = cells.filter(ImageFilter.MaxFilter(grow)).tobytes() if grow > 1 else px
        seen = bytearray(W * H)
        for start in (inside if inside is not None else range(W * H)):
            if not gx[start] or seen[start]:
                continue
            stack, comp = [start], []
            seen[start] = 1
            while stack:
                k = stack.pop()
                comp.append(k)
                y, x = divmod(k, W)
                for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                    n = ny * W + nx
                    if 0 <= ny < H and 0 <= nx < W and gx[n] and not seen[n] and (inside is None or n in inside):
                        seen[n] = 1
                        stack.append(n)
            core = [k for k in comp if px[k]]  # bbox from the real marks, not the growth
            if core:
                yield comp, core

    out = []
    todo = [(comp, core, 5) for comp, core in comps(5)]
    while todo:
        comp, core, grow = todo.pop()
        ys, xs = [k // W for k in core], [k % W for k in core]
        bw, bh = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        # tiny marks; a tall narrow figure (a skeleton side view) still counts
        if bh < H * 0.08 or bw < W * (0.05 if bh >= H * 0.25 else 0.12) or len(core) < 0.15 * bw * bh:
            continue
        if (min(xs) <= 1 or max(xs) >= W - 2) and bw < W * 0.25:
            continue  # a gutter shadow or the page edge of the scan
        if (min(ys) <= 1 or max(ys) >= H - 2) and bh >= H * 0.8:
            continue  # light falling across an old page, top to bottom; printed pictures sit in the margins
        r = pymupdf.Rect(min(xs) * C / f, min(ys) * C / f, (max(xs) + 1) * C / f, (max(ys) + 1) * C / f) & page.rect
        cover = _text_cover(raw, r)
        if cover >= (0.1 if bw * bh > 0.7 * W * H else 0.3):
            if grow > 1 and bw * bh > 0.3 * W * H:  # pictures joined to a text panel: split with less growth
                todo += [(c, k, grow - 2) for c, k in comps(grow - 2, set(comp))]
            continue  # print: a page of text (dark scan) or a tinted box of it
        # a tinted panel behind text is one flat tone filling its box; a picture spreads from
        # light to dark, and a line drawing in one ink colour leaves most of its box empty
        box = (int(r.x0 * f), int(r.y0 * f), int(r.x1 * f), int(r.y1 * f))
        if ImageStat.Stat(lum.crop(box), mask.crop(box)).stddev[0] < 12 \
                and ImageStat.Stat(mask.crop(box)).mean[0] > 255 * 0.5:
            continue
        if not layered and _lined(lum.crop(box), lum_cut):
            continue  # printed lines the OCR layer does not sit on: blank rows between them
        out.append(r)
    return sorted(out, key=lambda r: (r.y0, r.x0))


SENT_END = re.compile(r"[.!?:…][\"”’')\]]*$")
PAGE_NO = re.compile(r"[\[(]?[\d\s.\-–—]+[\])]?")
DROP_CAP = re.compile(r"[“\"‘']?[A-Z]|[“\"‘']")


def _letters(t: str) -> str:
    return re.sub(r"[^a-z]", "", (t or "").lower())


def _near_head(t: str, heads: set) -> bool:
    """A top line that is one of the book's running heads with a few letters misread by OCR."""
    from difflib import SequenceMatcher
    k = _letters(re.sub(r"\d", "", t))
    return len(k) >= 8 and any(abs(len(k) - len(h)) <= 4 and SequenceMatcher(None, k, h).ratio() >= 0.8
                               for h in heads)


def _furn_key(t) -> str:
    """A page head/foot line with its page number gone: digits, symbol-font glyphs (private use
    area) and control codes dropped, lowercased. "" when nothing but those was on the line."""
    if not isinstance(t, str):
        return ""
    t = re.sub(r"[\d-\x00-\x1f\x7f]", " ", t)
    return re.sub(r"\s+", " ", t).strip(" .-–—|").lower()
# a line set big by a noisy OCR layer is not a heading if it stops mid-phrase
OPEN_END = re.compile(r"(?:[,;\-–—]|\b(?:and|or|but|the|a|an|of|to|in|with|that|for))$", re.I)


def _ocr_layer(doc) -> bool:
    """True when the text is an invisible OCR layer over page scans (Internet Archive, ABBYY,
    ocrmypdf). Its blocks and font sizes are noisy, so paragraphs need looser rules."""
    n = len(doc)
    spans = invisible = 0
    for i in sorted({int(k * n / 10) for k in range(10)}) if n else []:
        for sp in doc[i].get_texttrace():
            spans += 1
            invisible += sp["type"] == 3
    return spans > 0 and invisible > spans * 0.5


def _mostly_scanned(doc) -> bool:
    """True when most pages are a page-sized image with next to no real text over it.

    ponytail: OCR used to run only when the PDF had no text at all, so one "Downloaded from"
    footer, a library stamp or a filled form field skipped OCR and the EPUB came out empty
    (reddit 11-05: a scanned form gave only the field's value). Invisible OCR layers have
    plenty of text, so they stay on the text path. Samples up to 20 pages.
    """
    n = len(doc)
    if not n:
        return False
    idx = sorted({int(k * n / 20) for k in range(20)})
    scans = 0
    for i in idx:
        page = doc[i]
        area = abs(page.rect) or 1
        img = sum(abs(pymupdf.Rect(im["bbox"]) & page.rect) for im in page.get_image_info())
        # ponytail: 0.6, was 0.8. Scans pasted into Word keep page margins and cover 74-77% (11-10)
        if img / area >= 0.6 and len(page.get_text().strip()) < 120:
            scans += 1
    return scans * 2 > len(idx)


def ocr_ok(texts) -> bool:
    """Enough OCR text to build a text EPUB instead of the image-only calibre fallback.

    ponytail: the bar scales with pages. A flat 200 chars sent every one-page scanned form
    (~130 chars) to calibre, reddit 11-06. 60 a page still drops photo books with stray OCR."""
    return bool(texts) and sum(len(t) for t in texts) > min(200, 60 * len(texts))


def _text_blocks(doc) -> list:
    """The text-path blocks, or [] when the PDF should go to OCR. One place, so /convert,
    manual_convert.py and test_regression.py all pick the same path."""
    return [] if _mostly_scanned(doc) or _garbled(doc) else list(_blocks(doc))


def _junk_share(text: str) -> float:
    """Share of non-space characters that are symbols, odd punctuation or private-use glyphs:
    non-ASCII ones (≤ ∞ ¨ ° «) plus the ASCII ones prose barely uses (~ ^ = ` < > # | \\).

    ponytail: letters never count, so Unicode Telugu, Hindi, Russian or Vietnamese stay text
    (0.05-0.09 measured 11-10); a dense English line of curly quotes and ligatures is 0.15."""
    s = [c for c in text if not c.isspace()]
    if not s:
        return 0.0
    # ponytail: ASCII control codes count too. A PDF24 OCR layer extracted as "\x02\x05\x01˖": 38%
    # control codes, 0.12 without them, and the text path made an EPUB of junk (The Stranger, 11-16)
    junk = sum(1 for c in s if (ord(c) > 0x7F and unicodedata.category(c)[0] in "SPC") or c in "~^=`<>#|\\"
               or ord(c) < 0x20 or c == "\x7f")
    return junk / len(s)


# Old non-Unicode Indian fonts. Kruti Dev and friends (Hindi) map glyphs onto plain ASCII
# ("dk;Z dj jgs gSa"), so the symbol share misses them; the font name does not.
LEGACY_FONTS = re.compile(r"kruti|devlys|chanakya|shusha|walkman|shree.?dev|aps.?dv|priyaanka|pallavi|"
                          r"natyamayuri|pragathi|anupama|tl-tt|hemalatha", re.I)
# common short words of Latin-script languages: real prose hits them every few words, font codes never
_ANY_STOP = set("the and of to in is was he that it a an de la el en y que los las le les et des du un une "
                "il est der die das und ist nicht ein eine den von zu mit het een van dat il di che non per "
                "o os as do da em um não com para por se".split())


def _legacy_font_share(doc, idx) -> float:
    """Share of the sampled text drawn in a known old non-Unicode Indian font."""
    old = total = 0
    for i in idx:
        for b in doc[i].get_text("dict").get("blocks", []):
            for line in b.get("lines", []):
                for sp in line["spans"]:
                    n = len(sp["text"].strip())
                    total += n
                    if LEGACY_FONTS.search(sp["font"]):
                        old += n
    return old / total if total else 0.0


def _garbled(doc) -> bool:
    """True when the text layer is font codes, not words: Indian-language books typeset in old
    non-Unicode fonts (Priyaanka, Anu) extract as "ã¨∂~°º^Õ=~°". Those pages go to OCR.

    ponytail: two Telugu novels (reddit 11-10) measured 0.26-0.43 on every page. Samples up to 12 pages."""
    n = len(doc)
    if not n:
        return False
    idx = sorted({int(k * n / 12) for k in range(12)})
    text = "".join(doc[i].get_text() for i in idx)
    if len(text) < 300:
        return False
    # ponytail: a font with no Unicode map extracts as spaces with a stray letter: Loya Nunchi
    # Sikharaniki (Gautami via iText, 11-18) is 2% non-space; real text is ~80%
    if sum(not c.isspace() for c in text) < 0.2 * len(text):
        return True
    return (_junk_share(text) > 0.2 or _legacy_font_share(doc, idx) > 0.5 or _no_language(text)
            or _broken_indic(doc, text))


def _no_language(text: str) -> bool:
    """Latin letters that are not any Latin-script language: old Indian fonts mapped onto ASCII
    and Latin-1 ("ÌÁÕ³ÁLiÂ¿Á[µj¶ NSµR¶V", TL-TTHemalatha, 11-10) came out as "Spanish"."""
    if _mixed_share(text) > 0.25:
        return True
    toks = [t for t in re.findall(r"[^\W\d_]+", text.lower()) if len(t) >= 2]
    latin = [t for t in toks if all(c.isascii() or "\u00c0" <= c <= "\u024f" for c in t)]
    if len(latin) < 150 or len(latin) < 0.7 * len(toks):
        return False
    return sum(t in _ANY_STOP for t in latin) < 0.03 * len(latin)


def _mixed_share(text: str) -> float:
    """Share of words that mix letters with digits or symbols ("6l$ssa", "6;aqg6c{F%a6€e5"): a
    junk text layer from an old Indian font or a bad Latin OCR over a Telugu scan (Ramayana, 11-10)."""
    toks = [t.strip(".,;:!?\"'()[]“”‘’-") for t in text.split()]
    toks = [t for t in toks if len(t) >= 3]
    if len(toks) < 50:
        return 0.0
    mixed = sum(1 for t in toks if any(c.isalpha() for c in t) and any(not c.isalpha() and not c in "-'’." for c in t))
    return mixed / len(toks)


def _word_set(text: str) -> set:
    # split on spaces: \w breaks Telugu words at every vowel sign
    return {w for t in text.split() if len(w := t.strip(".,;:!?\"'()[]“”‘’-—|")) >= 3}


def _broken_indic(doc, text: str) -> bool:
    """A Unicode Telugu/Hindi text layer whose vowel signs come out in the wrong order (made in
    Word with Mandali: "చేస్ానానడు" for "చేస్తానన్నాడు", 11-10). It reads as Telugu but not as words,
    so one page is OCR'd and compared; under 60% of its words found means OCR the book."""
    code = text_lang(text)
    tess = next((t for t, c in OCR_SCRIPTS.values() if c == code), None)
    if not tess or tess not in _tess_langs():
        return False
    i = max(range(len(doc)), key=lambda k: len(doc[k].get_text()) if abs(k - len(doc) // 2) < 6 else -1)
    words = _word_set(doc[i].get_text())
    if len(words) < 12:
        return False
    try:
        ocr = _word_set(_tess(doc[i].get_pixmap(dpi=_ocr_dpi(doc[i])).tobytes("png"), 1, 1, tess)[0])
    except Exception:
        return False
    return len(words & ocr) < 0.6 * len(words)


def doc_lang(doc) -> str:
    """EPUB language for a text-path book, from a sample of its pages."""
    n = len(doc)
    return text_lang("".join(doc[i].get_text() for i in sorted({int(k * n / 12) for k in range(12)})) if n else "")


NOTE_MARK_ONLY = re.compile(r"[*†‡§¶#⁰¹²³⁴⁵⁶⁷⁸⁹]{1,6}")


def _paragraphs(rows, bbox, ocr=False):
    """Split one PDF block's lines into paragraphs: [(y0, size, [line, ...]), ...].

    ponytail: OCR text layers (Internet Archive scans) group lines into blocks that ignore
    paragraphs, so one block can hold the end of one paragraph and the start of the next.
    An indented line after a finished sentence starts a new paragraph, and a short centered
    first line ("Author's Note" over the prose) is its own heading block.
    """
    # a page number the OCR layer put in the same block as the last paragraph line
    rows = [r for r in rows if not PAGE_NO.fullmatch(r[0])] or rows
    if not rows:
        return []
    bx0, bx1 = bbox[0], bbox[2]
    bw = max(bx1 - bx0, 1)
    left = min(r[2][0] for r in rows)
    groups = []
    for k, (txt, size, lb) in enumerate(rows):
        if groups and NOTE_MARK_ONLY.fullmatch(txt.strip()):
            groups[-1][2][-1] = groups[-1][2][-1].rstrip() + txt.strip()  # a raised "†" set as its own line
            continue
        lead, trail = lb[0] - bx0, bx1 - lb[2]
        centered = (k == 0 and len(rows) > 1 and len(txt) < 60 and lead > bw * 0.15
                    and trail > bw * 0.15 and abs(lead - trail) < bw * 0.12
                    and not SENT_END.search(txt))
        new_para = ocr and k > 0 and lb[0] - left > max(8, bw * 0.03) and SENT_END.search(rows[k - 1][0])
        # ponytail: a list or verse set one item per line in one block ("Sadness / Weakness / Confusion",
        # Paramattha 11-21) ran together as one paragraph. In a born-digital block a line that stops well
        # short of the block's edge ended its line on purpose; the next one starts a new paragraph unless
        # it carries on a word or a sentence in lowercase.
        if not ocr and k > 0 and not new_para:
            prev = rows[k - 1]
            new_para = bx1 - prev[2][2] > bw * 0.2 and not prev[0].endswith("-") and not txt[:1].islower()
        if not groups or new_para or (k == 1 and groups[-1][3]):
            groups.append([lb[1], size, [txt], centered])
        else:
            groups[-1][1] = max(groups[-1][1], size)
            groups[-1][2].append(txt)
    return [(y0, size, lines) for y0, size, lines, _ in groups]


def _heading_first(raw, body):
    """Move a heading the PDF wrote last back to the top of its page.

    ponytail: AO3/Kindle exports store a chapter's first paragraphs before the "Chapter 2"
    block that sits above them, so the opening landed at the end of the previous chapter (the
    first buyer's "formatting at the beginning of the chapters"). Only a trailing run that lies
    wholly above everything before it and holds a heading-size block moves; sorting the whole
    page by y reshuffled footnotes and tables in nonfiction.
    """
    def page_no(b):
        return PAGE_NO.fullmatch("".join(s["text"] for ln in b["lines"] for s in ln["spans"]).strip())
    text = [i for i, b in enumerate(raw) if b.get("type") == 0 and b.get("lines") and not page_no(b)]
    for cut in range(1, len(text)):
        head, tail = text[:cut], text[cut:]
        if max(raw[i]["bbox"][3] for i in tail) > min(raw[i]["bbox"][1] for i in head) + 2:
            continue
        if any(s["size"] >= body * 1.25 for i in tail for ln in raw[i]["lines"] for s in ln["spans"]):
            move = set(tail)
            return [raw[i] for i in tail] + [b for i, b in enumerate(raw) if i not in move]
        return raw
    return raw


def _place_fields(page, raw, body):
    """Filled form fields come last in PDF order and in an auto-sized font, so "Jane Doe" ended
    the page as a heading (reddit 11-05). Move each field block under the line it sits beside
    and set it in body type."""
    rects = [w.rect for w in page.widgets()] if page.first_widget else []
    if not rects:
        return raw

    def in_field(b):
        r = pymupdf.Rect(b["bbox"])
        return b.get("type") == 0 and any(abs(r & w) >= 0.5 * abs(r) for w in rects if abs(r))
    fields = [b for b in raw if in_field(b)]
    out = [b for b in raw if not in_field(b)]
    for f in sorted(fields, key=lambda b: b["bbox"][1]):
        for line in f.get("lines", []):
            for sp in line["spans"]:
                sp["size"] = body
        k = max((j + 1 for j, b in enumerate(out) if b["bbox"][1] <= (f["bbox"][1] + f["bbox"][3]) / 2), default=0)
        out.insert(k, f)
    return out


WORD3 = re.compile(r"[^\W\d_]{3,}")


def _junk_pages(doc) -> set:
    """Pages of an OCR layer whose words mostly appear nowhere else in the book.

    ponytail: Internet Archive scans of handwritten letters, faxes and photos OCR to
    "Gue Sf and ~-hewW muck gar". Real words recur across a book, OCR junk mostly doesn't,
    so the book is its own dictionary and no word list ships (Marcela, Divine Challenge 11-14).
    Those pages go in as pictures, which a reader can still read.
    """
    if len(doc) < 30:
        return set()
    words = {i: [w.lower() for w in WORD3.findall(pg.get_text("text"))] for i, pg in enumerate(doc)}
    df = Counter(w for ws in words.values() for w in set(ws))
    return {i for i, ws in words.items()
            if len(ws) >= 3 and sum(df[w] >= 3 for w in ws) < 0.6 * len(ws)}


IA_NOTICE = re.compile(r"digitized by the internet archive", re.I)
OFFPRINT = re.compile(r"e-?\s*offprint is for personal use only", re.I)
REFS_HEAD = re.compile(r"(references|bibliography|works cited|literature cited|sources)", re.I)


_GRAY = {}


def _page_gray(page):
    """One 72 dpi grayscale render per page, shared by every drop-cap ink test on it."""
    key = (id(page.parent), page.number)
    if key not in _GRAY:
        if len(_GRAY) > 4:
            _GRAY.clear()
        _GRAY[key] = page.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY)
    return _GRAY[key]


def _drop_cap(page, bbox) -> str:
    """The big first letter an OCR text layer left out, read off the page image, or "".

    ponytail: a scanned book with an OCR layer (Ageless Spine, 11-22 corpus) sets each chapter's first
    letter as a two-line drop cap. The layer has no text for it, and Google Drive's OCR loses it too,
    so chapters began "o say that", "ere's a quick start", "an you imagine". The letter sits left of
    the first line. Nothing here checks words: a book may spell anything on purpose (user, 11-23).
    What the picture shows decides: one tall letter shape (a sidebar's frame line is thin, the second
    line beside the same letter sees it cut off at the top), read alone by tesseract from three crops
    in black and white (gray paper made it read nothing), and at least two reads must agree."""
    x0, y0, x1, y1 = bbox
    h = max(6.0, y1 - y0)
    clip = pymupdf.Rect(max(0.0, x0 - 3.2 * h), y0 - 0.4 * h, x0 - 1, y0 + 2.8 * h) & page.rect
    if clip.is_empty or clip.width < h:
        return ""
    try:
        low = _page_gray(page)  # the ink test runs on one cached low-res render of the page
        z = low.width / page.rect.width
        ir = pymupdf.IRect(int(clip.x0 * z), int(clip.y0 * z), int(clip.x1 * z) + 1, int(clip.y1 * z) + 1)
        vals = [low.pixel(x, y)[0] for y in range(max(0, ir.y0), min(low.height, ir.y1))
                for x in range(max(0, ir.x0), min(low.width, ir.x1))]
        dark = sum(1 for v in vals if v < 110)
        if not vals or not 0.03 * len(vals) <= dark <= 0.35 * len(vals):
            return ""  # no ink (the line just starts lowercase) or a photo beside it, not a letter
        pm = page.get_pixmap(dpi=300, clip=clip, colorspace=pymupdf.csGRAY)
        w, ht, px = pm.width, pm.height, pm.samples
        ys = [y for y in range(ht) if any(px[y * w + x] < 128 for x in range(w))]
        xs = [x for x in range(w) if any(px[y * w + x] < 128 for y in range(ht))]
        hp = h * 300 / 72
        if not ys or ys[0] == 0 or ys[-1] - ys[0] < 1.5 * hp or xs[-1] - xs[0] < 0.5 * hp:
            return ""  # not one tall letter: a frame line, a bullet, or the lower half of a letter above
        reads = []
        for bottom in (2.8, 2.2, 1.9):
            c = pymupdf.Rect(clip.x0, clip.y0, clip.x1, y0 + bottom * h) & page.rect
            pm = page.get_pixmap(dpi=300, clip=c, colorspace=pymupdf.csGRAY)
            bw = pymupdf.Pixmap(pymupdf.csGRAY, pm.width, pm.height,
                                bytes(0 if v < 128 else 255 for v in pm.samples), False)
            pad = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.IRect(0, 0, bw.width + 80, bw.height + 80), False)
            pad.clear_with(255)
            bw.set_origin(40, 40)
            pad.copy(bw, bw.irect)
            r = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "10", "-c",
                                "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ"],
                               input=pad.tobytes("png"), capture_output=True, timeout=20)
            reads.append(r.stdout.decode("utf-8", "ignore").strip())
        best = max(set(reads), key=reads.count)
        return best if re.fullmatch(r"[A-Z]", best) and reads.count(best) >= 2 else ""
    except Exception:
        return ""


def _cap_rows(page, raw=None, xs=None) -> list:
    """[(row index in raw, first row text, letter)] for each block of the page's OCR layer whose
    first line lost its drop cap. ponytail: only a first line that starts lowercase and sits pushed
    in from the page's left edge is worth a look (an archive.org layer starts ~3,000 lines a book
    lowercase, 200 s of renders if all were checked); measured 11-22: drop-cap lines sit 1.7-2.5
    line heights in, 4+ is a caption or a centered line."""
    if page.rotation:
        return []
    raw = raw if raw is not None else page.get_text("dict")["blocks"]
    xs = xs if xs is not None else [ln["bbox"][0] for b in raw if b.get("type") == 0 for ln in b.get("lines", [])]
    margin = sorted(xs)[len(xs) // 4] if xs else 0
    got = []
    for bi, b in enumerate(raw):
        if b.get("type") != 0:
            continue
        rows = _ocr_rows(b)
        if rows and rows[0][0][:1].islower() \
                and 1.4 <= (rows[0][2][0] - margin) / max(6.0, rows[0][2][3] - rows[0][2][1]) <= 3.5:
            cap = _drop_cap(page, rows[0][2])
            if cap:
                got.append((bi, rows[0][0], cap))
    return got


def _ocr_rows(b):
    """An OCR block's lines as visual rows: [(text, size, bbox), ...].

    ponytail: an Internet Archive (LuraDocument) layer stores a justified line as one "line"
    per word or two, and guesses a size per word (4.2 to 11.4pt on one page of body text).
    Read as-is, every word was its own line and any line holding one 11pt word became a
    heading: 954 chapters for a novel (reddit 11-18). Words on the same baseline are one row
    again, sized by the size most of its letters have.
    """
    rows = []  # [x1, y0, y1, [spans], bbox]
    for line in b.get("lines", []):
        spans = [s for s in line["spans"] if s["text"]]
        if not "".join(s["text"] for s in spans).strip():
            continue
        x0, y0, x1, y1 = line["bbox"]
        r = rows[-1] if rows else None
        if r and r[1] <= (y0 + y1) / 2 <= r[2] and x0 >= r[0] - 2:
            if not r[3][-1]["text"].endswith(" ") and not spans[0]["text"].startswith(" "):
                r[3].append({"text": " ", "size": spans[0]["size"], "flags": 0})
            r[3].extend(spans)
            r[0] = max(r[0], x1)
            r[4] = (min(r[4][0], x0), min(r[4][1], y0), max(r[4][2], x1), max(r[4][3], y1))
        else:
            rows.append([x1, y0, y1, list(spans), tuple(line["bbox"])])
    out = []
    for _, _, _, spans, bbox in rows:
        txt = re.sub(r"\s{2,}", " ", "".join(_span_text(s) for s in spans)).strip()
        weights = sorted((s["size"], len(s["text"].strip())) for s in spans if s["text"].strip())
        if not txt or not weights:
            continue
        half, acc, size = sum(w for _, w in weights) / 2, 0, weights[-1][0]
        for sz, w in weights:
            acc += w
            if acc >= half:
                size = sz
                break
        out.append((txt, size, bbox))
    return out


def _blocks(doc):
    """Yield (page_no, y0, size, text) per text block, lines joined into one paragraph.

    ponytail: a visual line is not a paragraph. One wrapped paragraph came out as one
    <p> per line, which is exactly the "break paragraphs weird" complaint. PDF blocks
    are the paragraph unit, so join inside the block. Figure pages yield one extra block
    with size -1 and a (PNG bytes, caption) tuple as text.
    """
    body = _body_size(doc)
    ocr = _ocr_layer(doc)
    ligmap = _lig_map(doc)
    junk = _junk_pages(doc) if ocr else set()
    known = Counter(w.lower() for pg in doc for w in WORD3.findall(pg.get_text("text"))) if ocr else None
    # ponytail: a publisher's e-offprint (Springer) opens with a cover and a copyright notice
    # page before the article repeats its own title; they came out as two junk chapters.
    skip = max((k for k in range(min(3, len(doc))) if OFFPRINT.search(doc[k].get_text("text"))), default=-1)
    in_refs, ref = False, None  # inside a reference list: [page, y, size, lines] of the open entry
    # ponytail: a printed contents page ("THE BODY<tab>19") points at page numbers an e-book does not
    # have; with a bookmark outline the EPUB's own contents replaces it (Paramattha 11-21, 4 pages)
    toc_pages = {k for k in range(min(15, len(doc))) if doc[k].get_text("text").count("\t") >= 5} \
        if not ocr and _bookmarks(doc) else set()
    for i, page in enumerate(doc):
        if i <= skip or i in toc_pages:
            continue
        if ocr and (i in junk or (i == 0 and len(page.get_text("text").split()) < 40)):
            if IA_NOTICE.search(page.get_text("text")):
                continue  # the archive's own "Digitized by" page, not the book
            # cover and handwritten/fax pages: the picture, not their OCR junk
            pm = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
            yield i, 0.0, -1.0, (_fig_bytes(pm), "")
            continue
        raw = page.get_text("dict")["blocks"]
        raw = _place_fields(page, raw, body)
        if not page.rotation:
            raw = _heading_first(raw, body)
        for b in raw:
            for line in b.get("lines", []):
                _fix_line(line, ligmap)
                if not ocr:
                    _unspace(page, line)
                if not ocr:
                    for sp in line["spans"]:
                        _fix_math_span(sp)
            if not ocr:
                _merge_bands(b)
        figs = []
        texty = not ocr and len(page.get_text("text").strip()) > 200  # a real text layer, not a bare scan
        eq_rects = [] if not texty or page.rotation else [e[0] for e in _equations(raw, page.rect.height)]
        tables = _table_rects(page, raw, body, eq_rects) if texty and not page.rotation else []
        frs = [fr for fr in _figure_rects(page, raw, body, small=texty) if not any(t.contains(fr) for t in tables)]
        for fr in sorted(frs + tables, key=lambda r: (r.y0, r.x0)):
            fp = _page_rect(page, fr)
            cap, cap_page = _fig_caption(page, raw, fp)
            figs.append({"r": fr, "page": fp, "cap": cap, "cap_page": cap_page, "done": False})
        fig = figs[0]["r"] if figs else None
        xs = [ln["bbox"][0] for b in raw if b.get("type") == 0 for ln in b.get("lines", [])]
        caps = {bi: c for bi, _, c in _cap_rows(page, raw, xs)} if ocr else {}
        photos = _scan_photos(page, raw, known) if ocr and not fig and not page.rotation else []
        photo_rects = list(photos)
        eqs = [] if ocr or page.rotation else _equations(raw, page.rect.height)
        eqs = [e for e in eqs if not any(e[0].intersects(f["r"]) for f in figs)]  # labels stay in the figure
        eq_blocks = {k for _, ks in eqs for k in ks}
        eq_todo = sorted(eqs, key=lambda e: (e[0].y0, e[0].x0))
        for bi, b in enumerate(raw):
            while photos and photos[0].y0 <= b["bbox"][1]:
                ph = photos.pop(0)
                yield i, ph.y0, -1.0, (_fig_bytes(page.get_pixmap(dpi=SCAN_FIG_DPI, clip=ph)), "")
            if bi in eq_blocks:
                hit = next((e for e in eq_todo if bi in e[1]), None)
                if hit:  # the equation goes out where its first block was
                    eq_todo.remove(hit)
                    yield i, hit[0].y0, -1.0, _eq_image(page, hit[0], body)
                continue
            if photo_rects and b.get("type") == 0 and any(
                    p.contains(pymupdf.Point((b["bbox"][0] + b["bbox"][2]) / 2, (b["bbox"][1] + b["bbox"][3]) / 2))
                    for p in photo_rects) and not _wordy_line(
                    " ".join(s["text"] for ln in b.get("lines", []) for s in ln["spans"]), known):
                continue  # OCR read the photo itself as letters
            for f in figs:
                if not f["done"] and b["bbox"][1] > f["r"].y1:
                    pm = page.get_pixmap(matrix=pymupdf.Matrix(FIG_SCALE, FIG_SCALE), clip=f["page"])
                    yield i, f["r"].y0, -1.0, (_fig_bytes(pm), f["cap"])
                    f["done"] = True
            if figs:
                r = pymupdf.Rect(b["bbox"])
                center = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
                center = center * page.rotation_matrix if page.rotation else center
                if any(f["page"].contains(center) or (f["cap_page"] and f["cap_page"].contains(center))
                       for f in figs):
                    continue  # labels and caption are baked into the figure or its figcaption
            if b.get("type") != 0:
                continue
            rows = _ocr_rows(b) if ocr else []
            cap = caps.get(bi, "") if ocr and rows else ""
            if cap:
                rows[0] = (cap + rows[0][0], rows[0][1], rows[0][2])
            for line in [] if ocr else b.get("lines", []):
                txt = "".join(_span_text(s) for s in line["spans"]).strip()
                if txt:
                    rows.append((txt, _line_size(line), line["bbox"]))
            if not rows:
                continue
            edge = b["bbox"][3] < 60 or b["bbox"][1] > page.rect.height - 60  # running head/foot
            if in_refs and not ocr and not edge:
                if max(r[1] for r in rows) >= body * 1.12:
                    in_refs = False  # the next section's heading ends the list
                elif not re.match(r"\d{1,3}\s", rows[0][0]):  # "12 A note" is a footnote, not an entry
                    # ponytail: a reference list's PDF blocks cut entries anywhere (reddit 11-16,
                    # Springer paper): one block ended mid-entry, the next held two. Entries hang:
                    # first line at the column edge, the rest indented. Split on that instead.
                    for txt, size, lb in rows:
                        left = min((x for x in xs if lb[0] - 30 <= x <= lb[0]), default=lb[0])
                        if ref is None or lb[0] - left < 4:
                            if ref:
                                yield ref[0], ref[1], round(ref[2], 1), _join(ref[3])
                            ref = [i, lb[1], size, [txt]]
                        else:
                            ref[2] = max(ref[2], size)
                            ref[3].append(txt)
                    continue
            if ref and not edge:
                yield ref[0], ref[1], round(ref[2], 1), _join(ref[3])
                ref = None
            for y0, size, lines in _paragraphs(rows, b["bbox"], ocr):
                yield i, y0, round(size, 1), _join(lines)
            if REFS_HEAD.fullmatch(" ".join(r[0] for r in rows)):
                in_refs = True
        for f in figs:
            if not f["done"]:
                pm = page.get_pixmap(matrix=pymupdf.Matrix(FIG_SCALE, FIG_SCALE), clip=f["page"])
                yield i, f["r"].y0, -1.0, (_fig_bytes(pm), f["cap"])
        for ph in photos:
            yield i, ph.y0, -1.0, (_fig_bytes(page.get_pixmap(dpi=SCAN_FIG_DPI, clip=ph)), "")
    if ref:
        yield ref[0], ref[1], round(ref[2], 1), _join(ref[3])

def _suspect(chapters, pages: int) -> str:
    """Why this book's structure looks broken, or "" when it looks fine.

    ponytail: two r/ebooks readers (11-14 memoir, 207 chapters; 11-18 novel, 954 chapters)
    reported books that a glance would call broken. Most readers never write, so log the
    obvious cases and count them on /stats; if many come from real readers, an AI pass for
    those books only is worth paying for. A log line only, nothing changes for the reader.
    """
    n = len(chapters)
    if n > max(40, pages / 4):
        return "chapters"
    words = sum(len(t.split()) for ch in chapters for k, t in ch if k == "p" and isinstance(t, str))
    if n > 20 and words / n < 150:
        return "tiny-chapters"
    return ""


def _bm_norm(t: str) -> str:
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFC", t or "").lower())


def _bookmarks(doc) -> dict:
    """All PDF bookmark levels as {page index: [[level, title, norm, used], ...]}; {} when none.

    ponytail: Pages, Word and InDesign exports carry the author's own outline. Paramattha (11-21)
    set its 86 sub-headings at 13pt on 12pt body, under the size cut, so they came out as plain
    paragraphs and the contents listed 12 of 110 entries. The outline says which lines are headings.
    """
    try:
        toc = [(lvl, _clean(t).strip(), p - 1) for lvl, t, p, *_ in doc.get_toc() if t.strip() and p >= 1]
    except Exception:
        return {}
    pages = Counter(p for _, _, p in toc)
    # a bookmark per page ("1", "2", scan page lists) is navigation, not a heading outline
    if not toc or len(pages) > max(30, len(doc) * 0.8) or sum(len(_bm_norm(t)) <= 3 for _, t, _ in toc) > len(toc) / 2:
        return {}
    out = {}
    for lvl, t, p in toc:
        out.setdefault(p, []).append([min(lvl, 3), t, _bm_norm(t), False])
    return out


def _bm_match(bms: dict, page: int, t: str):
    """The unused bookmark on this page (or the next/previous) that this block's text is, else None."""
    n = _bm_norm(t)
    if len(n) < 3:
        return None
    for p in (page, page + 1, page - 1):
        for e in bms.get(p, []):
            if e[3]:
                continue
            if n == e[2] or (e[2].startswith(n) and len(n) >= 0.6 * len(e[2])) \
                    or (n.startswith(e[2]) and len(e[2]) >= 6 and len(n) <= len(e[2]) + 12):
                return e
    return None


def _bm_join(blocks, bms: dict):
    """Join a heading printed on two lines that PDF split into two blocks ("PART I: THE ES-" + "SENCE OF
    EXISTENCE", "DREAMS, ... BELOW THE" + "THRESHOLD OF CONSCIOUSNESS") when together they are one bookmark."""
    out = []
    for b in blocks:
        if out and b[2] > 0 and out[-1][2] > 0 and b[0] == out[-1][0] and isinstance(b[3], str) \
                and isinstance(out[-1][3], str) and len(out[-1][3]) < 120 and len(b[3]) < 120:
            a = out[-1][3]
            glued = a[:-1] + b[3] if re.search(r"[A-Za-z]-$", a) else a + " " + b[3]
            alone, both = _bm_match(bms, b[0], a), _bm_match(bms, b[0], glued)
            if both and (not alone or len(_bm_norm(glued)) <= len(both[2]) + 2 and _bm_norm(a) != alone[2]):
                out[-1] = (out[-1][0], out[-1][1], max(out[-1][2], b[2]), glued)
                continue
        out.append(b)
    return out


def _structure(blocks, doc):
    """blocks -> chapters: [[(kind, text), ...], ...]. shared by /convert and the landing proof.

    Footnote blocks (smaller type at the bottom of a page, starting with a marker) are moved
    to the end of the chapter they belong to, under a "Notes" block. Kept as ("fn", text).
    """
    # ponytail: weigh sizes by characters, not blocks. A paper's reference list and footnotes
    # are many short small-type blocks; counted per block they outvote the body, the body
    # size became 8.5 and every short 10pt quote line turned into a heading (reddit 11-16).
    long = Counter()
    for _, _, sz, t in blocks:
        if sz > 0 and len(t) > 40:
            long[sz] += len(t)
    body = long.most_common(1)[0][0] if long else Counter(sz for _, _, sz, _ in blocks).most_common(1)[0][0]
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
                           r"bibliography|references|appendix|index|foreword|preface|afterword|"
                           r"acknowledge?ments?|dedication|author[’']s note)\b[\s\dIVXLC.:-]*$", re.I)
    # ponytail: publisher page furniture changes per page (DOI, download date), so the repeated
    # header/footer counter never catches it; "Downloaded from <url>" is the common watermark.
    # Cambridge puts the "terms of use" line first in the same block, so match it anywhere.
    boiler = re.compile(r"downloaded from\s+https?:/{1,2}|^https?://doi\.org/|^Vol\.:\(0123456789\)$|"
                        r"^Publisher[’']s Note Springer Nature remains neutral|"
                        r"^jurisdictional claims in published maps and institutional affiliations", re.I)
    fn_more = re.compile(r"^Footnote (\d{1,3}) \(continued\)\s*")
    last_fn_page, open_note = -1, None  # open_note: (list, index) of the note the next small block extends

    def _note_add(loc, text):
        notes, k = loc
        if isinstance(notes[k], tuple):
            notes[k] = ("fn", notes[k][1] + " " + text)
        else:
            notes[k] += " " + text

    # strip repeated header/footer: same text on >50% pages at top/bottom edge
    ph = doc[0].rect.height
    tops = Counter(t for p, y, sz, t in blocks if y < 60)
    # ponytail: a running head sits above the text block. A fixed 60pt cut also took the first
    # line of a page set in small type: a reference at y=55 vanished (reddit 11-18 proofread,
    # the text starts at 54 there). Cut just above where body text starts on most pages.
    page_top = {}
    for p, y, sz, t in blocks:
        if sz > 0 and abs(sz - body) < 0.3 and len(t) > 40:
            page_top[p] = min(y, page_top.get(p, y))
    head_cut = min(60, sorted(page_top.values())[(len(page_top) - 1) // 2] - 6) if page_top else 60
    bots = Counter(t for p, y, sz, t in blocks if y > ph - 60)
    n = len(doc)
    # ponytail: c >= 2, or a one-page PDF loses its title as a 'repeated' header (reddit 11-06)
    banned = {t for t, c in list(tops.items()) + list(bots.items()) if c >= 2 and c > n * 0.5}
    # ponytail: "Preprint submitted to Elsevier Page 2 of 16" differs on every page by its
    # numbers, so the exact count missed it and it was glued into a paragraph running across
    # the page break (11-19 lead). Same line once the numbers go = the page footer.
    digits = lambda t: re.sub(r"\d+", "#", t)
    foot_keys = Counter(digits(t) for p, y, sz, t in blocks if y > ph - 60 and sz > 0 and len(t) < 160)
    banned |= {t for p, y, sz, t in blocks if y > ph - 60 and sz > 0 and re.search(r"\d", t)
               and re.search(r"[A-Za-z]{3}", t) and foot_keys[digits(t)] >= 3 and foot_keys[digits(t)] > n * 0.5}
    # ponytail: most books alternate running heads, the book title on left pages and the chapter
    # title on right ones, so neither is on half the pages; an OCR scan kept "SLOWLY BECOMING" /
    # "OF WATER AND THE SPIRIT" as headings on every page (reddit 11-18). A short line at the top
    # edge on 3+ pages is a running head there; the chapter's own title sits lower and stays.
    top_heads = {t for t, c in tops.items() if c >= 3 and len(t) < 80}
    # ponytail: an OCR layer misreads the page number in a running head ("60 Treasures of the
    # Kingdom", "go Treasures...", "The Trumpet Sounds ap"), so no two match; the ones set big
    # by OCR noise became headings (reddit 11-19). Same words once the short end tokens go.
    def top_key(t):
        ws = t.split()
        junk = lambda w: bool(re.search(r"\d", w)) or len(w) <= 2 or not re.search(r"[A-Za-z]{2}", w)
        while ws and junk(ws[0]) and len(ws) > 1:
            ws.pop(0)
        while ws and junk(ws[-1]):
            ws.pop()
        return " ".join(ws).lower()
    top_keys = Counter(top_key(t) for p, y, sz, t in blocks if y < 60 and sz > 0 and len(t) < 80)
    # ponytail: an archive.org scan (Reminiscences, 11-22 corpus) OCRs its running head differently on
    # many pages ("LAST SIXTY-FIVE YEARS. 13", "I;AST SIXTY-FIVE YEARS. 27", "C6 REMINISCENCES OFT HE"),
    # set larger than the text, so the misread ones became headings that cut paragraphs in two. Only a
    # line carrying its page number counts: a title page "THE FEASTING: DEAD" is not the running head.
    run_heads = {_letters(k) for k, c in top_keys.items() if c >= 3 and len(_letters(k)) >= 8}
    # ponytail: ebook-site PDFs (Planet eBook: 1984, Moby-Dick, The Prince, 11-22 QA) print the page
    # number in a symbol font (" Free eBooks at Planet eBook.com", "Moby Dick "), so every
    # page's footer differs and each is on every other page only, under the 50% cut. They stayed in the
    # text 13-22 times a book, spliced mid-word ("a list of fig Free eBooks... ures"), and the bare
    # glyph blocks between pages stopped the page-break join, so paragraphs split at every page end.
    blocks = list(blocks)
    foot_y = min(ph - 60, ph * 0.84)  # a 484pt ebook page has its footer at y=411, above ph - 60
    edge_keys = Counter(_furn_key(t) for p, y, sz, t in blocks
                        if sz > 0 and isinstance(t, str) and len(t) < 80 and (y < 60 or y > foot_y))
    furniture = {k for k, c in edge_keys.items() if k and c >= 3 and c > n * 0.2 and re.search(r"[a-z]{3}", k)}
    # ponytail: LaTeX books (Think Python/Stats, 11-22 QA) set the running head at y=61 on a letter page,
    # just under the 60pt cut, and it changes with the section ("2.4. Script mode", "Chapter 2. ..."),
    # so no text repeats enough. The place repeats: a short body-size line at one height above where
    # the text starts, on a third of the pages, is the running head. It split paragraphs at page ends.
    body_top = sorted(page_top.values())[(len(page_top) - 1) // 2] if page_top else 0
    head_rows = {}
    for p, y, sz, t in blocks:
        if sz > 0 and isinstance(t, str) and y < min(ph * 0.12, body_top - 4) and len(t) < 90 and sz < h2_cut:
            head_rows.setdefault(round(y / 2), set()).add(p)
    run_rows = {r for r, ps in head_rows.items() if len(ps) >= max(3, n * 0.3)}

    chapters, cur, cur_notes = [], [], []
    drop = None  # (letter, page) of a drop cap waiting for the paragraph it starts
    ocr = _ocr_layer(doc)
    bms = {} if ocr else _bookmarks(doc)
    if bms:
        blocks = _bm_join(list(blocks), bms)
    list_item = re.compile(r"^(?:[-–•·*▪◦]|\d{1,3}[.)]|#)\s")
    # "Chapter 1 — Childhood" in body type; OCR reads the 1 as | or l ("Chapter | - Childhood")
    ch_title = re.compile(r"^(chapter|part)\s+(\d{1,3}|[ivxlc]{1,7}|\|)\s*[—–:.\-]+\s*\S.{0,80}$", re.I)
    # ponytail: count chapter lines only. An anthology scan's Introduction / Preface / Prologue
    # made 4 "named" lines, so its story titles never split and 30 stories ran on in 5 chapters
    # (reddit 11-19, "the short stories do not start on a fresh page")
    named = sum(1 for _, _, sz, t in blocks if sz > 0 and len(t) < 120
                and (ch_title.match(t) or (head_word.match(t) and re.match(r"(chapter|part|book)\b", t, re.I))))
    known = Counter(w.lower() for _, _, sz, t in blocks if sz > 0 for w in WORD3.findall(t))

    def caps_title(t):
        """A short line in capitals, mostly letters: "JACKKNIFED", "JACK BE NIMBLE. JACK BE QUICK".
        Such a title is in the book once, so the junk check (words must recur) can't apply to
        it; junk is rarely mostly letters in capitals, and "HELLOJACKHELLOJACK" (a run-together
        screen message) has a word too long for a title."""
        letters = [c for c in t if c.isalpha()]
        ws = WORD3.findall(t)
        # the novel's screen messages are capitals too, but run on as sentences
        breaks = len(re.findall(r"\w[.!?]\s", t))
        if t[:1].islower() or breaks > 1 or (breaks and len(t.split()) > 6):
            return False
        return (bool(ws) and len(letters) >= 4 and len(t.split()) <= 12
                and sum(c.isupper() for c in letters) >= 0.7 * len(letters)
                and len(letters) >= 0.7 * len(t.replace(" ", "")) and max(len(w) for w in ws) <= 15
                and not SENT_END.search(t.rstrip("!") if not breaks else t))  # "A SPOILED PRIEST!" (OCR)

    def size_head(t):
        """A line set big by an OCR layer, is it a heading? Bible verses and quoted letters
        set large end in a full stop; OCR junk ("; oe ¢ pee ee") has no real words."""
        if not ocr:
            return True
        if caps_title(t):
            return True
        ws = WORD3.findall(t)
        # ponytail: a paragraph's first line, a little bigger by OCR noise, is a full line of
        # mixed-case prose ("From the fourth floor of the mathematics"), opens with a quote or
        # holds a sentence break. Headings are short or set in capitals (reddit 11-18 novel).
        prose = len(t) >= 35 or t[:1] in "\"“‘'" or re.search(r"\w[.!?][\"”’]?\s+[A-Z\"“]", t)
        return (len(t.split()) <= 12 and not SENT_END.search(t) and not t[:1].islower()
                and not prose and bool(ws) and sum(known[w.lower()] >= 3 for w in ws) >= 0.6 * len(ws))

    def open_para():
        """Index in cur of the paragraph a new block may continue: the last item, or the last
        paragraph with only pictures after it (at most 3). -1 when there is none.

        ponytail: a photo set mid-paragraph (Ageless Spine, 11-22 corpus: 25 of its 29 page-end
        splits) sits between the two halves, so the half after it became a new paragraph."""
        k = len(cur) - 1
        while k >= 0 and cur[k][0] == "img" and len(cur) - 1 - k < 3:
            k -= 1
        return k if k >= 0 and cur[k][0] == "p" and isinstance(cur[k][1], str) else -1

    def continues(t, sz):
        # OCR layers size each line differently, so a mid-paragraph line can look like a heading
        # by font size alone; an open sentence before it or a lowercase start says otherwise.
        k = open_para()
        if k < 0:
            return False
        if ocr and sz >= h2_cut and caps_title(t):
            return False  # a chapter title after a page that ends mid-sentence
        prev = cur[k][1]
        if list_item.match(t) or SENT_END.search(prev):
            return False
        if re.search(r"[a-z]-$", prev) or t[:1].islower():
            return True
        if t[:1] in "—…" and t[1:2].islower():
            return True  # "on that team" / "—no,” he paused": dialogue picked up after a dash
        # a born-digital block without a full stop is a list or a cell; past a picture, only a
        # lowercase start or a broken word says the sentence goes on
        return ocr and len(prev) >= 50 and k == len(cur) - 1

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
        if ocr:  # ponytail: a scan's ornament before a title OCRs to "/ ", "» ", "¥ " (reddit 11-19)
            t = re.sub(r"^[/»¥]\s+(?=\S)", "", t)
        if y < 60 and t in top_heads and not re.match(r"(chapter|part|book)\b", t, re.I):
            continue
        if ocr and y < 60 and len(t) < 80 and len(top_key(t).split()) >= 2 and top_keys[top_key(t)] >= 3 \
                and not re.match(r"(chapter|part|book)\b", top_key(t)):
            continue
        if ocr and y < 60 and len(t) < 80 and run_heads and re.search(r"\d", t) \
                and not re.match(r"(chapter|part|book)\b", t, re.I) and _near_head(t, run_heads):
            continue  # the same running head with a letter or two misread ("I;AST SIXTY-FIVE YEARS. 27")
        if t in banned or boiler.search(t) or PAGE_NO.fullmatch(t):
            continue  # ponytail: page numbers ("12", "[12]", "- 12 -")/running heads dropped, no config
        if (y < 60 or y > foot_y) and len(t) < 80 and (_furn_key(t) in furniture or not _furn_key(t)) \
                and not re.match(r"(chapter|part|book)\b", t, re.I):
            continue  # a footer/head with a symbol-font page number, or that glyph alone (11-22)
        if run_rows and sz < h2_cut and len(t) < 90 and {round(y / 2) - 1, round(y / 2), round(y / 2) + 1} & run_rows \
                and not ocr:
            continue
        if (y < 60 or y > foot_y) and re.fullmatch(r"[ivxlcdm]{1,7}", t.strip(), re.I) and t.strip().lower() != "i":
            continue  # a roman page number in the front matter ("ix", "xiv")
        if not re.sub(r"[\s\ue000-\uf8ff\x00-\x1f\x7f]", "", t):
            continue  # an icon in a symbol font (Pro Git's note/tip glyphs) is not a heading
        if not ocr and drop:
            # ponytail: a drop cap is its own big block ("I" at 28pt, then "t was a bright cold day"),
            # so it became a chapter heading and the first sentence lost its letter (1984, 11-22 QA)
            d, dp = drop
            drop = None
            if dp == pno and t[:1].isalpha():
                first = re.match(r"[^\W\d_]+", t).group(0)
                spaced = d in ("I", "A") and len(first) >= 3 and known[first.lower()] >= 2 \
                    and not known[(d + first).lower()]
                t = d + (" " if spaced else "") + t
            else:
                cur.append(("p", d))
        if not ocr and sz >= h2_cut and len(t) <= 2 and DROP_CAP.fullmatch(t):
            drop = (t, pno)
            continue
        # ponytail: a running head carries its page number, so the text differs on every page
        # and the repeated-header counter misses it; it sits at the top edge in smaller type.
        if y < head_cut and sz < fn_cut and len(t) < 120 and re.search(r"\d", t):
            continue
        bm = _bm_match(bms, pno, t) if bms and len(t) < 160 else None
        if bm:
            # the author's outline: level 1 starts a chapter, levels 2-3 are its sections ("s2", "s3",
            # headings that also get a contents entry)
            bm[3] = True
            if bm[0] == 1:
                flush()
                cur.append(("h1", t))
            else:
                cur.append((f"s{bm[0]}", t))
            continue
        # shortcut: marker + small font + bottom half is a heuristic; a numbered list set in
        # smaller type at the foot of a page can be moved into Notes. upgrade to a ruled-off
        # / superscript-marker check if that shows up in real books.
        foot = sz < fn_cut and y > doc[pno].rect.height * 0.55 and body_pages[pno] >= 3
        if foot and fn_more.match(t):
            # ponytail: Springer carries a long note onto the next page under "Footnote 1
            # (continued)", the label and the text as separate blocks. The text starts lowercase,
            # so it was glued to the body paragraph above it (reddit 11-16/11-18). Find the note,
            # keep it open, and the small blocks under the label on this page go into it.
            n, rest = fn_more.match(t).group(1), fn_more.sub("", t)
            open_note = None
            for notes in (cur_notes, *reversed(chapters)):
                k = next((j for j in range(len(notes) - 1, -1, -1)
                          if (notes[j][1].startswith(n + " ") and notes[j][0] == "fn" if isinstance(notes[j], tuple)
                              else notes[j].startswith(n + " "))), None)
                if k is not None:
                    open_note = (notes, k)
                    break
            if open_note is None:
                cur_notes.append(n)
                open_note = (cur_notes, len(cur_notes) - 1)
            if rest:
                _note_add(open_note, rest)
            last_fn_page = pno
        elif foot and fn_mark.match(t) and re.search(r"[a-z]{3}", t):
            cur_notes.append(t)
            open_note = (cur_notes, len(cur_notes) - 1)
            last_fn_page = pno
        elif foot and open_note and pno == last_fn_page and open_note[1] < len(open_note[0]):
            _note_add(open_note, t)  # an unmarked small block under a note: its address, its rest
        elif (head_word.match(t) or ch_title.match(t)) and len(t) < 120:
            flush()
            cur.append(("h1", re.sub(r"^(chapter|part)\s+\|", r"\1 1", t, flags=re.I)))
        elif continues(t, sz):
            # ponytail: a block that picks up a sentence the last one left open (a new page, or
            # an OCR text layer that cut the paragraph into blocks) is the same paragraph. Pictures
            # between the halves stay where they are, after the joined paragraph.
            k = open_para()
            prev = cur[k][1]
            glue = prev[:-1] if prev.endswith("-") and prev[-2:-1].isalpha() else \
                prev if t[:1] in "—…" else prev + " "
            cur[k] = ("p", glue + t)
        elif sz >= h2_cut and len(t) < 120 and not OPEN_END.search(t) and ocr and not size_head(t):
            if any(c.isalpha() for c in t) and WORD3.search(t):
                cur.append(("p", t))  # big but not a heading: a verse, a quoted letter
        elif sz >= h1_cut and len(t) < 120 and not OPEN_END.search(t):
            if not (ocr and named >= 3):
                flush()  # ponytail: an OCR scan with its own "Chapter N" lines splits on those only
            cur.append(("h1", t))
        elif sz >= h2_cut and len(t) < 120 and not OPEN_END.search(t):
            if not (ocr and named >= 3):
                flush()
            cur.append(("h2", t))
        else:
            cur.append(("p", t))
    flush()
    # ponytail: a heading printed on two lines can come out as heading "... THE ES-" plus a caps scrap
    # "SENCE" in body type (Paramattha 11-21). A heading ending mid-word takes the scrap back.
    for ch in chapters:
        k = 0
        while k + 1 < len(ch):
            kind, t = ch[k]
            nk, nt = ch[k + 1]
            caps_line = kind == "p" and isinstance(t, str) and len(t) < 80 and t.upper() == t
            if (kind in ("h1", "h2", "s2", "s3") or caps_line) and isinstance(t, str) and re.search(r"[A-Z]-$", t) \
                    and nk == "p" and isinstance(nt, str) and len(nt) < 60 and nt.upper() == nt:
                ch[k] = (kind, t[:-1] + nt)
                del ch[k + 1]
                continue
            k += 1
    # a few words above the title ("OPEN FORUM", a journal's section label) were a chapter of
    # their own; put them under the title instead
    if len(chapters) > 1 and all(k == "p" for k, _ in chapters[0]) \
            and sum(len(t) for _, t in chapters[0]) < 60 and chapters[1][0][0] in ("h1", "h2"):
        label = chapters.pop(0)
        chapters[0][1:1] = label
    # ponytail: a section that starts mid-page takes the notes printed at that page's foot,
    # even when their markers sit in the section before (notes 22-23 landed under References,
    # reddit 11-16). Move a note back when only the previous chapter carries its marker.
    for k in range(1, len(chapters)):
        def says(ch, sup):
            return any(sup in t for kind, t in ch if kind != "fn" and isinstance(t, str))
        keep, back = [], []
        for item in chapters[k]:
            m = re.match(r"(\d{1,3}) ", item[1]) if item[0] == "fn" else None
            sup = m.group(1).translate(SUP) if m else ""
            (back if sup and not says(chapters[k], sup) and says(chapters[k - 1], sup) else keep).append(item)
        if back:
            chapters[k] = keep
            chapters[k - 1].extend(back)
    # ponytail: a chapter title set in a decorative face OCRs to junk ("LIF6 BeCINSXT KJXNSI")
    # while the same title as a plain running head reads clean ("LIFE BEGINS AT NANSI"). Running
    # heads are dropped above, but they still spell the title, so a heading close to one takes it.
    if ocr and top_heads:
        from difflib import SequenceMatcher
        for ch in chapters:
            for k, (kind, t) in enumerate(ch):
                if kind in ("h1", "h2") and isinstance(t, str) and t not in top_heads and len(t) >= 8:
                    best = max(top_heads, key=lambda h: SequenceMatcher(None, t.upper(), h.upper()).ratio())
                    if SequenceMatcher(None, t.upper(), best.upper()).ratio() >= 0.6:
                        ch[k] = (kind, best)
    return chapters


@app.post("/convert")
async def convert(request: Request, f: UploadFile = File(...), title: str = Form(""), author: str = Form(""),
                  email: str = Form(""), preview: str = Form(""), free: str = Form("")):
    throttle(request)
    ref = ref_of(request)
    key = shelf_key(request)  # ponytail: a paying subscriber gets a bigger ceiling, no account needed
    raw = await f.read()
    kb_in = len(raw) // 1024
    # ponytail: a worker killed for memory leaves no log line, so note the size before the heavy work
    event("start", request, kb=kb_in, paid=bool(key))
    def work():
        nonlocal author  # ponytail: reassigned from the PDF metadata below
        # ponytail: ?paid=CHECKOUT_ID is the $5 one-book, converted on the spot by the converter
        cid = (request.query_params.get("paid") or "")[:80]
        digest = hashlib.sha256(raw).hexdigest()[:32]
        book_max = onebook_ok(cid, digest) if cid else 0
        book = bool(book_max)
        if cid and not book:
            log(False, 0, kb_in, 0, "paid-refused", ref, request=request)
            raise HTTPException(402, "this checkout is not confirmed as paid, or it already converted a "
                                f"different book. Reply to the Polar receipt or email {SHELF_MAIL}")
        freeb = bool(free) and not key and not book and freebook_ok(free[:40], digest)
        if free and not freeb and not key and not book:
            log(False, 0, kb_in, 0, "free-refused", ref, request=request)
            raise HTTPException(402, "this free book was already used on a different file. The next book is $5, "
                                "or $10 for 30 days of unlimited books")
        if freeb:
            book_max = SHELF_MAX_PAGES
        paid = bool(key or book or freeb)
        max_pages = SHELF_MAX_PAGES if key else (book_max or MAX_PAGES)
        max_mb = SHELF_MAX_MB if paid else MAX_MB
        if len(raw) > max_mb * 1024 * 1024:
            log(False, 0, kb_in, 0, "too big", ref, email.strip()[:120], request=request)
            raise HTTPException(413, f"over {max_mb}MB - one book is $5 (up to 2,000 pages)"
                if not paid else f"over {max_mb}MB, that is the top of the paid tier, email {SHELF_MAIL} and we will raise your limit")
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
        total = len(doc)
        # ponytail: a long book gets its first pages free, so the $5 is for a book they have already seen work
        cut_pages = preview == "1" and not paid and total > max_pages
        cap = ""  # ponytail: "pages:380" / "ocr:246" tells the page to pitch $5 after the free part, one upload instead of two
        if cut_pages:
            log(False, total, kb_in, 0, "too many pages", ref, email.strip()[:120], request=request)  # same cap stat as before
            cap = f"pages:{total}"
            doc.select(range(max_pages))
        if len(doc) > max_pages:
            n0 = len(doc)
            doc.close()
            log(False, n0, kb_in, 0, "too many pages", ref, email.strip()[:120], request=request)
            raise HTTPException(413, f"over {max_pages} pages ({n0} here) - one book is $5 (up to 2,000 pages)"
                if not paid else f"{n0} pages is over the {max_pages}-page limit of this purchase. Email {SHELF_MAIL} "
                f"with your checkout ID and we will raise the limit for your book, no extra charge")

        def done(data: bytes, pages: int, kind: str):
            log(True, pages, kb_in, len(data) // 1024, kind, ref, email.strip()[:120], request=request)
            if book:
                onebook_use(cid, digest)
                event("paid_convert", request, checkout_id=cid, pages=pages)
            if freeb:
                freebook_use(free[:40], digest)
                event("free_convert", request, pages=pages)
            hdr = {"Content-Disposition": _epub_disp(f.filename)}
            if cap:
                hdr["X-Cap"] = cap
            return Response(data, media_type="application/epub+zip", headers=hdr)

        npages = len(doc)
        meta = doc.metadata or {}
        # ponytail: most PDFs carry their own /Title and /Author, so the two fields are usually a no-op
        safe_title = (title or (meta.get("title") or "").strip()
                      or (f.filename or "book").rsplit(".", 1)[0])[:120] or "book"
        if "_" in safe_title and " " not in safe_title:
            safe_title = safe_title.replace("_", " ")  # "Into_the_Blue" on the Kindle shelf -> "Into the Blue"
        author = (author or (meta.get("author") or "").strip())[:120]
        if DRIVE_REFRESH and _ocr_layer(doc):
            # ponytail (11-21): a scan with someone else's OCR layer is a scan, so it is read again
            # (layer_scan_pages) under the scan limits: 20 free pages, the whole book paid. Its old
            # layer was the book before, 150 free pages of misreads and handwriting.
            cut = preview == "1" and not paid and npages > FREE_OCR_PAGES
            if npages > FREE_OCR_PAGES and not paid and not cut:
                doc.close()
                log(False, npages, kb_in, 0, "ocr-wall", ref, email.strip()[:120], request=request)
                raise HTTPException(402, f"scanned PDF ({npages} here) - free OCR reads the first "
                                    f"{FREE_OCR_PAGES} pages, the whole book is $5")
            if cut:
                cap = f"ocr:{total}"
                if not cut_pages:
                    log(False, total, kb_in, 0, "ocr-wall", ref, email.strip()[:120], request=request)
                doc.select(range(FREE_OCR_PAGES))
            elang = doc_lang(doc)
            pages = layer_scan_pages(doc, elang, key)
            event("layer_scan", request, pages=len(doc), total=total, paid=paid, ok=bool(pages))
            texts = [t for t, _ in pages or []]
            if pages and ocr_ok(texts):
                figs = _scan_figures(doc, pages, {})
                cover = scan_cover(doc, texts, figs)
                chapters = ocr_chapters(texts, figs, pdf_toc(doc))
                if cut:
                    chapters.append([("h1", "The rest of this book"),
                        ("p", f"This is the free preview: the first {FREE_OCR_PAGES} of {total} pages. "
                              "The whole book is $5 at epub.ftak.net, converted on the spot.")])
                data = build_epub(chapters, safe_title, author[:120], elang, cover)
                doc.close()
                return done(data, len(texts), "layer-preview" if cut else "layer")
            npages = len(doc)  # Drive failed: the old layer, as before (cut to the free part if cut)
        blocks = _text_blocks(doc)
        if not blocks:
            # scanned PDF: OCR is the only thing that helps before falling back
            cut = preview == "1" and not paid and npages > FREE_OCR_PAGES
            if npages > FREE_OCR_PAGES and not paid and not cut:
                doc.close()
                log(False, npages, kb_in, 0, "ocr-wall", ref, email.strip()[:120], request=request)
                raise HTTPException(402, f"scanned PDF ({npages} here) - free OCR reads the first "
                                    f"{FREE_OCR_PAGES} pages, the whole book is $5")
            if cut:
                cap = f"ocr:{total}"
                if not cut_pages:
                    log(False, total, kb_in, 0, "ocr-wall", ref, email.strip()[:120], request=request)
                doc.select(range(FREE_OCR_PAGES))  # ponytail: the free taste of a long scan, then the wall
            if npages <= (min(PAID_OCR_MAX_PAGES, max_pages) if paid else FREE_OCR_PAGES) or cut:
                tlang, elang = ocr_lang(doc)
                pics, confs = {}, {}
                pages = ocr_doc(doc, layout=True, lang=tlang, pics=pics, confs=confs) or []
                # ponytail (11-23): a $3/$5 one-book buyer has a checkout, not a key, so their scan stayed raw
                # Tesseract ("many characters garbled", refund asked, 74-p scan 11-22). Every paid run gets
                # Drive's free re-read of unsure pages; the AI pass still needs a Library key.
                if paid and pages:
                    reread_pages(doc, pages, confs, elang, key)
                texts = [t for t, _ in pages]
                if ocr_ok(texts):
                    figs = _scan_figures(doc, pages, pics)
                    cover = scan_cover(doc, texts, figs)
                    chapters = ocr_chapters(texts, figs, pdf_toc(doc))
                    if cut:
                        chapters.append([("h1", "The rest of this book"),
                            ("p", f"This is the free preview: the first {FREE_OCR_PAGES} of {total} pages. "
                                  "The whole book is $5 at epub.ftak.net, converted on the spot.")])
                    data = build_epub(chapters, safe_title, author[:120], elang, cover)
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
                                f"{SHELF_MAIL} and we will raise the limit for your file"
                if big else "scanned PDF — OCR found no readable text (photo of handwriting?)")
        chapters = _structure(blocks, doc)
        why = _suspect(chapters, len(doc))
        if why:
            event("suspect", request, why=why, pages=len(doc), ch=len(chapters), ocr_layer=_ocr_layer(doc))
        if cut_pages:
            chapters.append([("h1", "The rest of this book"),
                ("p", f"This is the free preview: the first {max_pages} of {total} pages. "
                      "The whole book is $5 at epub.ftak.net, converted on the spot.")])

        data = build_epub(chapters, safe_title, author[:120], doc_lang(doc))
        _lint_later(raw, data, ref, npages)
        # ponytail: nothing stored, files die with request — matches their privacy pitch for free
        doc.close()
        return done(data, npages, "pages-preview" if cut_pages else "")

    def traced():
        # ponytail: a crash used to leave only a traceback on stdout, so /stats never saw it.
        # log the exception type and where it broke; the file itself is never kept
        try:
            if kb_in > BIG_MB * 1024:
                import fcntl
                with open(BIG_LOCK, "w") as lk:
                    fcntl.flock(lk, fcntl.LOCK_EX)  # released when the file closes
                    return work()
            return work()
        except HTTPException:
            raise
        except Exception as e:
            log(False, 0, kb_in, 0, crash_reason(e), ref, email.strip()[:120], request=request)
            raise

    if request.headers.get("x-job") == "1":
        # ponytail: the page polls /job/<id>, so no request runs past railway's 5-minute idle cut
        jid = _job_start(traced, email, re.sub(r"[\r\n]", " ", f.filename or "book.pdf")[:80])
        return JSONResponse({"job": jid}, status_code=202)
    # ponytail: off the event loop, so one heavy book no longer freezes the site for everyone else
    return await run_in_threadpool(traced)

def _job_write(jid: str, **state):
    tmp = JOB_DIR / f"{jid}.json.tmp"
    tmp.write_text(json.dumps({"t": time.time(), **state}))
    tmp.replace(JOB_DIR / f"{jid}.json")


def _job_sweep():
    now = time.time()
    try:
        for f in JOB_DIR.iterdir():
            age = now - f.stat().st_mtime
            if f.suffix == ".got" and age > GOT_GRACE:
                _job_drop(f.stem)
            elif age > JOB_TTL:
                # ponytail: a 2,000-page paid scan runs for well over an hour; its status file must outlive the TTL
                if f.suffix == ".json" and age < JOB_MAX_RUN and '"running"' in f.read_text()[:200]:
                    continue
                f.unlink(missing_ok=True)
    except OSError:
        pass


def _mail_link(jid: str, to: str, name: str):
    """Mail the download link if the tab was closed: the epub is still here MAIL_AFTER seconds later."""
    time.sleep(MAIL_AFTER)
    if not (JOB_DIR / f"{jid}.epub").exists() or (JOB_DIR / f"{jid}.got").exists():
        return  # ponytail: downloaded in the tab already, no mail
    body = (f"Your EPUB of {name} is ready:\n\nhttps://epub.ftak.net/job/{jid}/epub\n\n"
            "The link works once and for about an hour after the conversion finished, then the file is deleted. "
            "If it has expired, upload the PDF again.\n\nReply to this email if anything looks wrong.\n\n"
            "Krishav, pdf2epub")
    ok, err = _send_mail(to, f"Your EPUB is ready: {name}", body)
    if ok:
        event("link_mailed", None, job=jid[:6], sender=ok)
    else:
        event("link_mail_failed", None, job=jid[:6], err=err)


def _job_run(jid: str, work, email: str = "", name: str = "book"):
    _job_write(jid, state="running")
    try:
        resp = work()
        (JOB_DIR / f"{jid}.epub").write_bytes(resp.body)
        _job_write(jid, state="done", cap=resp.headers.get("x-cap", ""))
        to = (email or "").strip()
        if RESEND_KEY and re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}", to):
            threading.Thread(target=_mail_link, args=(jid, to, name), daemon=True).start()
    except HTTPException as e:
        _job_write(jid, state="error", status=e.status_code, detail=str(e.detail))
    except Exception:
        traceback.print_exc()
        _job_write(jid, state="error", status=500, detail="the converter failed on this file. Email it to "
                   f"{SHELF_MAIL} so we can fix the converter for it and rerun it")


def _job_start(work, email: str = "", name: str = "book") -> str:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    _job_sweep()
    jid = secrets.token_urlsafe(18)
    _job_write(jid, state="queued")
    try:
        (JOB_DIR / f"{jid}.name").write_text(name)
    except OSError:
        pass
    _JOB_POOL.submit(_job_run, jid, work, email, name)
    return jid


def _job_path(jid: str, ext: str) -> Path:
    if not re.fullmatch(r"[0-9A-Za-z_-]{20,40}", jid):
        raise HTTPException(404, "no such job")
    return JOB_DIR / f"{jid}.{ext}"


@app.get("/job/{jid}")
def job_status(jid: str):
    p = _job_path(jid, "json")
    try:
        return JSONResponse(json.loads(p.read_text()), headers={"Cache-Control": "no-store"})
    except (OSError, ValueError):
        raise HTTPException(404, "no such job")


@app.get("/job/{jid}/epub")
def job_file(jid: str):
    p = _job_path(jid, "epub")
    if not p.exists():
        raise HTTPException(404, "no such job")

    got = _job_path(jid, "got")
    if not got.exists():
        # ponytail: first download starts a 10 min clock, then the epub is gone ("deleted after the download")
        got.touch()
        t = threading.Timer(GOT_GRACE, _job_drop, args=(jid,))
        t.daemon = True
        t.start()
    try:
        name = _job_path(jid, "name").read_text()
    except OSError:
        name = "book.pdf"
    return FileResponse(p, media_type="application/epub+zip", headers={"Content-Disposition": _epub_disp(name)})


def _job_drop(jid: str):
    for ext in ("epub", "json", "got", "name"):
        (JOB_DIR / f"{jid}.{ext}").unlink(missing_ok=True)


@app.exception_handler(HTTPException)
async def http_err(request: Request, exc: HTTPException):
    if "text/html" in request.headers.get("accept", ""):
        return err_page(str(exc.detail), exc.status_code)
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

import translate  # noqa: E402  ponytail: ftak.net/translate-pdf backend, kept out of this file
app.include_router(translate.router)


@app.middleware("http")
async def translate_cors(request: Request, call_next):
    # ponytail: errors (400/402/429) must carry the header too, or ftak.net can't show the message
    resp = await call_next(request)
    origin = request.headers.get("origin", "")
    if request.url.path.startswith("/translate") and origin in translate.ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
    return resp

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, port=8000)
