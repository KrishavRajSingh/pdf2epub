# pdf2epub

Live: https://epub.ftak.net/

Free PDF to EPUB with real chapters + TOC for Kindle/Kobo. Text PDFs, no signup.

Run: `pip install -r requirements.txt && uvicorn app:app`
Deploy: Railway via `Dockerfile` (includes Calibre fallback).
Privacy: files in memory only, counts logged.
