"""Free OCR through Google Drive: upload a page image as a Google Doc, read the text back, delete it.

Bake-off on 10 hard Telugu pages (11-11), similarity to a hand-checked reference:
Tesseract 0.87, Surya 0.94, Drive 0.95, Gemini Flash-Lite 0.97. Drive is free, so the library jobs
(Shelf, 1000-book readers) send their low-confidence pages here. Runs on this Mac with the `gws` CLI
and the owner's Google login, never on the site.
"""
import json
import re
import subprocess
import tempfile
import uuid
from pathlib import Path


def _gws(*args, cwd=None, timeout=120):
    # ponytail: gws refuses --upload/-o paths outside its working directory, so it runs inside the temp dir
    r = subprocess.run(["gws", "drive", "files", *args], capture_output=True, text=True, timeout=timeout, cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-300:] or r.stdout.strip()[-300:])
    return r.stdout


def drive_ocr(img: bytes, lang: str = "te", tries: int = 3) -> str | None:
    """Text of one page image, paragraphs separated by blank lines; None when Drive fails."""
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "page.jpg"
        src.write_bytes(img)
        out = Path(d) / "page.txt"
        for k in range(tries):
            fid = None
            try:
                meta = {"name": f"pdf2epub-ocr-{uuid.uuid4().hex[:10]}", "mimeType": "application/vnd.google-apps.document"}
                res = _gws("create", "--params", json.dumps({"ocrLanguage": lang, "fields": "id"}),
                           "--json", json.dumps(meta), "--upload", src.name, "--upload-content-type", "image/jpeg", cwd=d)
                fid = json.loads(res)["id"]
                _gws("export", "--params", json.dumps({"fileId": fid, "mimeType": "text/plain"}), "-o", out.name, cwd=d)
                return _clean(out.read_text("utf-8", "replace"))
            except Exception as e:
                print(f"gdrive: try {k + 1} failed: {e}", flush=True)
                continue
            finally:
                if fid:
                    try:
                        _gws("delete", "--params", json.dumps({"fileId": fid}))
                    except Exception:
                        pass
    return None


def _clean(text: str) -> str:
    # ponytail: the export starts with a BOM and a "____" rule where the image sat; each line is a paragraph
    lines = [l.strip().lstrip("﻿") for l in text.splitlines()]
    return "\n\n".join(l for l in lines if l and not re.fullmatch(r"_+", l))
