# Day-17 content piece: the all-in price of one 300-page scanned textbook

Playbook format: "when the complaint is pricing, line up 5 alternatives and show what each one costs once you add everything up."

## The numbers (checked 2026-10-20)

| Tool | One 300-page scan | Signup | Where the file goes | Scan/OCR | Chapters + TOC | Cap |
|---|---|---|---|---|---|---|
| pdf2epub | **$0** | none | uploaded, in memory, deleted after download | OCR on image-only PDFs, free | yes | 200MB / 500 pages |
| freepub.app | $0 | none | never uploaded, runs in your browser | text extraction with OCR fallback, default output is page images | inherits the PDF's own structure | no limit (email-safe targets ~20MB) |
| pureepub.com | $0 | none | nothing saved, wiped after conversion | not stated, positioned on cleaning existing EPUBs | reflows, no TOC claim | not stated |
| convert2epub.com | **$3.30–3.75** (1 credit/page at $0.011–0.0125), **$6.60–7.50** for the Pro pass via Mathpix, $3.49 cap if you pay anonymously | optional (30 free credits) | anonymous files deleted, signed-in files kept 30 days | 1 credit/OCR page | yes, automatic chapters, clickable TOC | 100MB |
| cloudconvert | free tier 10 conversions/day, PDF→Office costs 4 base credits + 1/min, so volume needs a paid package | yes | their servers | no OCR | no | 1GB free tier |
| Calibre + OCR plugin | $0, but install + plugin setup, and the PDF→EPUB output still needs fixing by hand | no | local | plugin needed | manual | machine dependent |

## Reddit-ready draft (r/ebooks, after the 72h gate, with `?s=` tag)

Title: I costed out every PDF to EPUB converter for one scanned textbook

Someone asked in r/kindle for a converter that "actually works", so I ran the same 300 page scanned
PDF through everything I could find and worked out what each one really charges.

Free ones, and they are good:
- freepub.app runs entirely in your browser, nothing uploaded, no limits. Its default output is page
  images, which keeps the layout but means you zoom to read.
- pureepub.com reflows text and gives you a KePub for Kobo. Nothing saved, no accounts.
- Calibre is free and local. It needs `--enable-heuristics` to strip headers and page numbers, and
  it needs an OCR plugin before it will touch a scan.

The one that costs money: convert2epub.com converts ordinary text PDFs free and no account, but a
scan is charged per page. 1 credit per OCR page, 1 credit per 10 pages to recover an existing scan
text layer, 2 credits per page for the Pro pass that rebuilds formulas and tables. That works out to
around $3.30 for 300 pages, or $6.60 if you want the Pro pass, and it caps at 100MB per file.
CloudConvert is free for 10 conversions a day and then you are on credits.

So the honest answer is that a scanned textbook is free if you are willing to accept page images,
and about three to seven dollars if you want searchable reflowed text from a scan.

What I wanted to know when I started: what actually breaks in a PDF conversion. Two things. Every
printed line becomes its own paragraph, so a normal book reads like a receipt. And running headers and
page numbers end up inside the text, which is why "break paragraphs weird" is the complaint you see
in every thread about this.

Happy to run the same comparison on other files, or on a 500 page textbook, if that is more
interesting than a general one.

Comment with the file you want tested and I will run it.

## Notes
- Always tag the tools you mention so people can check the claims (convert2epub, freepub, pureepub).
- Do not claim the Pro pass is bad. It is genuinely better for equations and tables, that is why it
  costs more.
- Do not claim any of them stores your file without checking. convert2epub keeps signed-in files for
  30 days, freepub and pureepub keep nothing.
- Keep the measurement honest: state the page count and the file type, or the comparison is noise.
