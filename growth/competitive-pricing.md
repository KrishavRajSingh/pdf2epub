# Competitive pricing (checked 2026-10-20, prices as seen today)

Five alternatives + us, priced the way a real user hits it: **one 300-page scanned textbook**, one try, no account.

| Tool | Cost for a 300-page scan | Signup | Where the file goes | Scans/OCR | Chapters + TOC | Output formats | Size cap |
|---|---|---|---|---|---|---|---|
| **pdf2epub** (us) | **$0** | none | uploaded, in memory only, deleted after download | OCR on image-only PDFs (free) | yes, detected headings → clickable TOC | EPUB3 | 200MB / 500 pages |
| **freepub.app** | $0 | none | never uploaded, runs in your browser | text extraction with OCR fallback; default output is page images | inherits the PDF's own structure, no TOC builder | fixed-layout EPUB (pixel pages), optional text-only EPUB | no limit, but email-safe targets ~20MB |
| **pureepub.com** | $0 | none | nothing saved, wiped after conversion | not stated (positioned on cleaning existing EPUBs) | reflows, no TOC claim | EPUB for Kindle, KePub for Kobo | not stated |
| **convert2epub.com** | **$3.30-3.75** (Standard OCR, 1 credit/page at $0.011-0.0125) · **$6.60-7.50** (Pro recognition via Mathpix, 2 credits/page) · $3.49 cap if you pay anonymously | optional (30 free credits with account; first 10 OCR pages free without) | anonymous files deleted after download; signed-in files kept 30 days | 1 credit/OCR page, 1 credit/10 pages to recover an existing scan text layer | yes, automatic chapter detection, clickable TOC, header/footer removal | EPUB, AZW3, MOBI, PDF, EPUB→Kindle, translation, Chrome extension | 100MB/file |
| **cloudconvert** | free tier is 10 conversions/day; PDF→Office costs 4 base credits + 1/min, so volume needs a paid package/subscription (subscriptions up to 50% off packages) | yes for paid | their servers | no OCR | no | many | 1GB free tier |
| **Calibre** (desktop) | $0 | no | local | needs an OCR plugin, none installed by default | you build it by hand | EPUB, AZW3, MOBI | machine dependent |

Also in the wild: PDF Craft / Oomol (paid, macOS, 200MB/1500-page caps), pdf2epub.ai (free sample then paid), FreeReader, jumapps pdf2epub (Android app), any2epub (web→EPUB), Okular, Xodo.

## What this means for us
1. **The free lane is taken and it is not us.** freepub.app and pureepub.com already promise free, local, no account, nothing stored. Their pitch is identical to ours, and freepub's default output is page images, which is why "text-based EPUB" mode exists.
2. **convert2epub is the real competitor**, and it is ahead on features (Pro/Mathpix for equations and tables, translation, EPUB→Kindle/AZW3/MOBI, Chrome extension, a 30-day library, its own "converter comparison" SEO page). Its gap is the one we should attack: **OCR on scans costs credits**, $0.011-0.0125 per page, so a 300-page scan is ~$3.30 and a Pro pass is ~$6.60. Its file cap is 100MB against our 200MB.
3. **Our wedge is narrow and real**: a scanned book converted free, with no signup, no credits, nothing stored, real chapters and a TOC, up to 200MB / 500 pages. Say exactly that and nothing else.
4. **The $10/mo paid tier has a number to beat.** convert2epub sells 1,000 credits for $11, which is 1,000 OCR pages. So $10/mo has to mean **1,000 scanned pages included**, no credit maths, plus whatever convert2epub charges on top: batch, library, TOC repair, notes sync. Sell "1,000 pages of scans a month for $10, nothing stored" rather than "credits".
5. **The honest weak spot**: academic PDFs with formulas, figures and two columns. convert2epub's Pro (Mathpix) genuinely does that better. Do not claim it. Our answer there should be "read it on a tablet", which is what the thread answers say anyway.

## Source links
- https://freepub.app/ (page last modified 2026-06-25)
- https://convert2epub.com/ + /pricing + /faq (credit math read from the FAQ and pricing page today)
- https://pureepub.com/ (from the r/kindle post `1wo017r`, 46↑/31c)
- https://cloudconvert.com/pricing
- Thread where convert2epub is recommended: r/ebooks `1x39d2e`; freepub.app is recommended in r/kindle `1sa7guk` as freepub.app (the community-made converter)
