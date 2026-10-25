# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two confirmed audiences, in priority order:

1. **Power reader (primary).** Owns many large books, often a textbook or a library collection. One
   real session converted 68 PDFs / 12,908 pages in 32 minutes and hit the 500 page cap seven times.
   Reads on Kindle, Kobo, Boox, PocketBook, iPad or a phone. Wants many files converted with no
   per-file ceiling, and will pay to keep going.
2. **One-book reader.** Has a single PDF they want to read as a book: a textbook, a paper, a scan of
   a print book, a course file. Not a publisher, not a developer, and does not want to install
   software.

Both are technical-adjacent: they know Calibre, KOReader and Send to Kindle, and are tired of
installing things. They judge a converter by looking at the first paragraph. They most often arrive
from a link in a forum, newsletter or social post.

Assumed, not measured: the site is read on a phone more often than on a desktop.

## Product Purpose

Turn a PDF into an EPUB that reads like a book, free, with no account and no watermark, so the file
can go straight onto an e-reader. The paid offers exist only for files and volumes that pass the
free ceiling.

Success:

- Within 10 seconds the visitor understands the file will not be kept and no account is needed.
- Within 30 seconds they have an EPUB whose paragraphs read like a book, with a working table of
  contents.
- They come back for the next file, and send it to the friend who complains about their e-reader.
- For the current stretch of work: the first paying customer.

## Positioning

Free, no account, no watermark, files never stored, and the free path stays free and open. That is
the standing contrast with freepub.app and pureepub.com, which gate the useful output behind a
signup or a subscription. The second differentiator is the repair work: real paragraphs, running
heads and page numbers stripped, headings turned into chapters, a real table of contents, figures
and maps kept, scans OCR'd. A neighboring converter could copy either claim alone, not both, because
the free tier is the pitch rather than a trial.

## Operating Context

- Inputs are text PDFs and scans; a physical book can be photographed with a phone at `/scan`
  (up to 60 pages per batch).
- Output targets: Send to Kindle by email with the subject "convert", USB copy, Apple Books, Kobo,
  KOReader, PocketBook.
- Traffic arrives from Reddit, Hacker News and third-party newsletters. A deepculture Substack issue
  put the site in its Bonus slot and produced most of the conversions. `utm_source` / `?s=` tags
  identify the channel.
- Analytics is the log file (`conversions.log`, one JSON line per event) plus a stdout copy. There is
  no account system and no database. Pages keep a random id in localStorage (`v`) and send funnel
  steps to `/e`; checkout links go through `/go/{offer}`. `/funnel?k=FUNNEL_KEY` shows people per
  step by first-touch source.
- Deploys are owned by Railway (Dockerfile) and can be paused for hours at a time.
- Conversion is synchronous; OCR runs inside the request.

## Capabilities and Constraints

- Free tier: 200MB / 500 pages per text PDF. Scans: OCR free for the first 20 pages
  (`FREE_OCR_PAGES`); a longer scan gets a 402 with the $5 offer and a free 20-page preview.
- $5 one-book: paid up front, then the buyer lands on `/onebook` with an upload box and the book
  converts on the spot (up to 2,000 pages, OCR up to 600 pages in one request). One book per
  checkout, keyed by the file's hash, so re-running the same file is free. Needs `POLAR_TOKEN` on
  the host; without it every checkout reads as unconfirmed and falls back to email.
- $10/month Shelf: a mailed URL key (`?k=KEY`) lifts the per-file ceiling to 2,000 pages / 500MB.
  The Shelf page also promises batch conversion and Kindle delivery; those are not implemented.
- No accounts, no database. Keys are lines in a file on the volume; the checkout id prevents a
  second key being minted on refresh.
- Stack constraint: single FastAPI file, no build step, no client framework, no npm. Tesseract for
  OCR and Calibre as a fallback engine, both system binaries, so the host must be a Docker host, not
  a serverless function.
- Not a library manager, not a reader app, not a DRM tool, not a document AI. One file in, one EPUB
  out.
- Undecided: which paid offer produces the first customer. The $5 one-book is the current priority.

## Brand Commitments

Name: pdf2epub, live at https://epub.ftak.net. Voice is plain and technical-adjacent, with no
marketing adjectives; file facts and numbers are shown as evidence in monospace. The promise carried
in the copy and footer stays binding: "No account, no watermark, files deleted after download."

Existing visual direction, preserve unless a redesign is explicitly requested: a precision
instrument rather than a startup landing page. Dark and quiet, one accent. The hero shows the
product's real output for a real file rather than a screenshot.

## Evidence on Hand

- Real funnel data and its reading: `growth/money-state.md` (2026-10-24), `conversions.log`,
  `server.log`.
- One session of 68 PDFs / 12,908 pages in 32 minutes, seven cap rejects at 528 to 570 pages, no
  payment.
- 439 real human visits, 85 conversions, 0 paid, as of 2026-10-24.
- The product is its own demo: the hero figures are computed from a real sample PDF on every page
  load, and `/sample.pdf` backs the "Try it with a sample PDF" path.
- Absent: testimonials, case studies, customer logos, press coverage, paid-customer numbers. Do not
  fabricate any of them.

## Product Principles

1. The free path stays free and open for text PDFs. Paid exists past the free ceiling, and for OCR
   past the first 20 pages, because OCR is the expensive work.
2. Show the output, not adjectives. Numbers and file facts are the proof.
3. No account, no watermark, no stored files. Privacy is a product feature, not a policy page.
4. Meet the buyer at the moment of intent (the cap wall), not in a funnel.
5. One file in, one EPUB out. Do not grow into a library manager, reader or document AI.
