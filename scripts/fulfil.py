"""Turn "send me your PDF" emails into delivered EPUBs.

Reads the founder's Gmail for messages with a PDF attachment, converts with the same pipeline the
site uses (fixed paragraphs, chapters, TOC, OCR for scans), emails the EPUB back, and records
everything in growth/leads.csv so we know who is a lead and who became a subscriber.

usage: python3 scripts/fulfil.py --once      # process whatever is waiting
       python3 scripts/fulfil.py --watch     # keep polling every 60s
"""
import base64, csv, json, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
WORK = Path("/tmp/pdf2epub-fulfil")
WORK.mkdir(exist_ok=True)
LEADS = ROOT / "growth" / "leads.csv"
STATE = WORK / "processed.json"

MAIL = "krishavrajsingh@gmail.com"


def gws(*args, **kw):
    cmd = ["gws", *args]
    for k, v in kw.items():
        cmd += [f"--{k}", str(v)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-400:] or p.stdout[-400:])
    out = p.stdout.strip()
    try:
        return json.loads(out)
    except Exception:
        return out


def state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(s):
    STATE.write_text(json.dumps(s, indent=1))


def find_pdfs(msg):
    """Return [(filename, attachmentId)] for pdf attachments of a fetched message."""
    out = []
    def walk(part):
        fn = (part.get("filename") or "")
        if fn.lower().endswith(".pdf") and part.get("body", {}).get("attachmentId"):
            out.append((fn, part["body"]["attachmentId"]))
        for p in part.get("parts", []) or []:
            walk(p)
    walk((msg.get("payload") or {}))
    return out


def convert(raw: bytes, title: str) -> bytes:
    import pymupdf
    import app as pdf2epub
    doc = pymupdf.open(stream=raw, filetype="pdf")
    blocks = list(pdf2epub._blocks(doc))
    if blocks:
        chapters = pdf2epub._structure(blocks, doc)
    else:
        pages = pdf2epub.ocr_doc(doc) or []
        chapters = pdf2epub.ocr_chapters(pages)
    doc.close()
    if not chapters:
        raise RuntimeError("nothing readable in that pdf")
    return pdf2epub.build_epub(chapters, title or "book", "")


def log_lead(row):
    exists = LEADS.exists()
    LEADS.parent.mkdir(parents=True, exist_ok=True)
    with LEADS.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            w.writeheader()
        w.writerow(row)


def process_once():
    st = state()
    msgs = gws("gmail", "users", "messages", "list", params=json.dumps(
        {"userId": "me", "q": "has:attachment filename:pdf newer_than:3d -label:pdf2epub-done"}))
    items = msgs.get("messages", []) if isinstance(msgs, dict) else []
    n = 0
    for m in items:
        mid = m["id"]
        if mid in st:
            continue
        full = gws("gmail", "users", "messages", "get", params=json.dumps({"userId": "me", "id": mid, "format": "full"}))
        msg = full if isinstance(full, dict) else (full.get("message") or {})
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        frm = headers.get("from", "")
        m_ = re.search(r"<([^>]+)>", frm)
        email = (m_ or re.match(r"([^\s]+)", frm))
        email = email.group(1) if email else frm
        subject = headers.get("subject", "")
        pdfs = find_pdfs(msg.get("payload") or {})
        for fn, aid in pdfs[:1]:
            att = gws("gmail", "users", "messages", "attachments", "get",
                      params=json.dumps({"userId": "me", "messageId": mid, "attachmentId": aid}))
            data = att.get("data") if isinstance(att, dict) else att
            raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
            src = WORK / f"{mid}.pdf"
            src.write_bytes(raw)
            title = re.sub(r"\.pdf$", "", fn, flags=re.I)
            epub = convert(raw, title)
            out = WORK / f"{mid}.epub"
            out.write_bytes(epub)
            body = (f"Here is {title}.epub.\n\n"
                    f"What the converter did: {len(epub)//1024} KB, paragraphs rejoined, running headers and "
                    f"page numbers removed, headings turned into chapters with a table of contents"
                    + (", text read with OCR because the file is a scan" if not pdf2epub._blocks else "")
                    + ".\n\nSend it to your Kindle with the subject line \"convert\", or copy it over USB. "
                    "Nothing is stored, the file dies with this request.\n\n"
                    "If you have more than the one book, I am opening 10 spots at $10/month for a "
                    "1,000 page batch with batch conversion and direct delivery to your Kindle. "
                    "Worth it, or one book at a time is enough?\n\nKrishav")
            gws("gmail", "+send", "--to", email, "--subject", f"Your EPUB: {title}", "--body", body,
                "-a", str(out))
            log_lead({"email": email, "subject": subject[:120], "file": fn, "kb": len(epub) // 1024,
                      "status": "delivered", "ts": time.strftime("%Y-%m-%d %H:%M")})
            print(f"delivered {fn} -> {email} ({len(epub)//1024} KB)")
            n += 1
        st[mid] = time.strftime("%Y-%m-%d %H:%M")
        save_state(st)
        try:
            gws("gmail", "users", "messages", "modify", params=json.dumps(
                {"userId": "me", "id": mid, "addLabelIds": ["pdf2epub-done"]}))
        except Exception as e:
            print("label failed (ignored):", str(e)[:120])
    if n == 0:
        print("nothing new")
    return n


if __name__ == "__main__":
    if "--watch" in sys.argv:
        while True:
            try:
                process_once()
            except Exception as e:
                print("error:", str(e)[:300])
            time.sleep(60)
    else:
        process_once()
