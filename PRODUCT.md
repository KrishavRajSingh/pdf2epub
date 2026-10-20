# pdf2epub — product context

Free PDF to EPUB converter. Live at https://epub.ftak.net. No account, no watermark, files processed
in memory and deleted after download. Free tier: text PDFs and scans (OCR) up to 200MB / 500 pages.
Paid tier (not built): 1,000 scanned pages a month for $10.

## Who it is for
Someone who owns a PDF they want to read as a book: a textbook, a paper, a scan of a print book they
cannot find in digital form, a course PDF. They read on a Kindle, Kobo, Boox, PocketBook, iPad or a
phone. They are not a publisher, not a developer, and they do not want to install software.

## What "success" looks like
- Within 10 seconds they understand the file will not be kept and no account is needed.
- Within 30 seconds they have an EPUB whose paragraphs read like a book, with a working table of
  contents.
- They come back for the next file, and they send it to the friend who keeps complaining about
  their e-reader.

## What it is not
- Not a library manager, not a reader app, not a DRM tool.
- Not a document AI. One file in, one EPUB out.
- Not a subscription funnel on the free path. The free path stays free and open, that is the whole
  pitch against freepub.app and pureepub.com.

## Assumptions (inferred from the brief, not from an interview)
- The audience is technical-adjacent (they know Calibre, KOReader, Send to Kindle) but tired of
  installing things. The copy can use their vocabulary.
- They judge a converter by looking at the first paragraph. Proof beats adjectives.
- The site is read on a phone more often than a desktop, and often from a link inside a forum.

## Constraints
- Single FastAPI file, no build step, no client framework, no npm. Anything that needs a bundler is
  out.
- Tesseract for OCR, Calibre as a fallback engine. Both are system binaries, so the host must be a
  Docker host, not a serverless function.
- The log file is the analytics store. It also prints to stdout so the numbers survive a host move.
- Deploys are owned by a third party (Railway) and can be paused for hours at a time.

## Visual direction
A precision instrument, not a startup landing page. Dark, quiet, one accent. Numbers and file facts
in monospace because the audience reads them as evidence. The hero shows the product's actual output
for a real file instead of a screenshot, so the page cannot drift from what the tool does.
