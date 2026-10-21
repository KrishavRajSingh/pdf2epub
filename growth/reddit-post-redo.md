# Reddit post redo (r/ebooks) — draft for the next slot, not posted yet

Why the first post got 1 upvote: no proof, nothing to try in 5 seconds, and a title that promises a tool instead of describing a problem. The two tool posts that work in these subs (r/ereader 314↑/23c, r/ebooks 96↑/45c) both do the same four things:

1. Start with a personal problem, not a product.
2. Name what you tried and why it failed.
3. Say what is different, with a number or a limit.
4. Give one clear thing to try and ask for the specific test case.

Draft (post in r/ebooks, flair "Self Promotion", plain link `https://epub.ftak.net/?s=post-ebooks-2`):

---
Title: I built a PDF→EPUB converter because scanned textbooks kept turning into garbage on my Kindle

I kept buying PDFs I'd never read: course syllabi, a 400-page reference, papers with no EPUB anywhere. On a 6" screen a PDF is a photocopy you have to zoom into, so they just sat there.

Calibre and the online converters all produced the same thing for me. Paragraphs split across lines with the hyphen still attached, page numbers repeated at the top of every chunk, and no table of contents, so scrolling to chapter 12 was a guessing game.

So I built one that does the boring parts properly:

- Running headers and page numbers get stripped instead of landing inside the paragraph
- Words split across lines get rejoined
- Headings get detected and turned into a real clickable table of contents
- If the PDF is a photo of a page (scanned book), it runs OCR instead of giving up
- Chapters are detected, so the Kindle's jump-to-chapter works

Free, no signup, up to 200MB / 500 pages. The file is processed in memory and deleted after the download, so nothing is kept.

What it doesn't do: two-column academic PDFs with formulas come out in the wrong reading order, and for those I read the PDF on a tablet.

If you've got a PDF that usually breaks converters, a scanned textbook, or a file with a weird layout, I'd like to see how it handles it. Tell me what broke and I'll fix that case.
---

## Before posting
- [ ] Post the 3 real before/after screenshots (mangled PDF page vs same page as EPUB with the TOC open). The first post had none, and that is the main reason it did not take.
- [ ] Make sure a stranger can try it in 5 seconds with no file of their own. Add a "try it with a sample PDF" button on the landing page (also the fix for the 0.9% visit→upload rate in `/stats`).
- [ ] Wait for the current post to clear its 72h gate before posting again in r/ebooks. Do not post the same thing twice in one sub.
- [ ] Alternative slots, in order of preference: r/xteinkereader (pre-flight first, need a live tool-post precedent), r/ereader (a tool post survived there at 314↑, but the sub says no advertising, so only post if a live tool post is visible today).
- [ ] r/Annas_Archive: no. It removed the last post in 30 minutes.
- [ ] r/Calibre: only with an **AI CONTENT DISCLOSURE** header, per their rules post `1wx55zn`.

## What to measure
`/stats` → `ok_by_ref` for the tag `post-ebooks-2` at 1h, 24h, 72h. Continue only if the post stays up and produces conversions on that ref. Compare against the HN number for calibration: one HN post brought 836 visits but 0 Reddit-tagged conversions, so the bar for a Reddit post is lower than you think: 10 conversions in 72h.
