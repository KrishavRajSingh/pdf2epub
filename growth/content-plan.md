# pdf2epub — customer-first growth plan (playbook run, 2026-10-20)

Method actually run (not a summary of the idea):
1. 20 seed-stage startups with announcements dated 2026-01-20 → 2026-07-20 (3–9 months before today) → `seed_raises.csv` (21 rows incl. 2 date-conflicted).
2. Picked 5 whose customer is *someone who owns PDFs/books and wants them readable on their own device*.
3. Read each founder's recent X posts + every reply under them → `question-sheet.csv`.
4. Supplemented with X search ("convert pdf to epub", "kindle conversion", …) and Reddit threads (r/ebooks, r/kindle, r/ereader, r/Calibre) because the founders' own reply threads turned out to be noise.

---

## 1. The 5 startups (same customer as pdf2epub)

| Startup | Seed | Announced | Their customer | Why it is the same customer | X handles (read) |
|---|---|---|---|---|---|
| **Hyperknow** | $1M (ZhenFund) | Jan 2026 | students who upload their own syllabus/slides/PDFs to get a 1:1 AI tutor | same file, same person: a PDF of course material that must become something you can actually read/study | @leslie_rh7 (1.1k), @yi1inz, @hyperknow_ai (1.9k) |
| **Pensive** | $6.8M (Mayfield) | Feb 2026 | professors/TAs grading student submissions (PDFs, scans, handwriting) | same file, opposite end of the pipe: a PDF that arrives unreadable and has to be read properly | @yoonseok_yang (3.6k), @trypensive |
| **Sinai.ai** | $1.45M (KAUST/DisrupTech) | Apr 2026 | readers of books + students who want quizzes/study guides from a chapter | a book has to be a real, navigable file before any of that works | @ahmadKaamel, @Sinaidotai |
| **Spoken** | ~$500K | Jan 2026 | indie authors who publish EPUBs and audiobooks | same artefact (EPUB), opposite direction: they produce the file we convert into | @SpokenPress (founder @philmarshall exists but is empty) |
| **Littlebird** | $11M (Lotus Studio) | Mar 2026 | knowledge workers drowning in PDFs | adjacent: same file class, biggest X reach of the five for audience borrowing | @alapshah1 (8.8k), @LittlebirdAI (3.1k) |

Considered and dropped: **READO** (€1M seed, Mar 2026) and **Voxa** (€4M seed, Apr 2026) — closest customer of all (ebook readers) but @reado_app is dead (6 followers, 0 posts) and Voxa's obvious handle belongs to another company. **Plotsy** ($1.5–2M, Jun/Aug 2026) — book readers, but the raise date conflicts and the founder's X account is a personal sci-fi account.
Sources for every raise: `seed_raises.csv` → `source` column.

## 2. What the harvest actually found (the honest bit)

- **Founder reply threads gave almost nothing.** 202 threads read under the founders'/companies' own posts (Hyperknow, Pensive, Sinai.ai, Littlebird, Spoken, Rely, Plotsy). Strict filter for product-shaped questions: **42 found, 15 answered by the founder, 27 unanswered — and on manual read most of those 27 are macro/policy chat ("AI is a bubble", "how would AI cause limitless energy"), not product asks.** Replies under AI founders in 2026 are crypto/engagement bots, "let's connect", and praise. X search with keyword + `to:` filters returns the same noise.
- **The vein is the customer, not the founder.** Reddit threads (r/ebooks, r/kindle, r/ereader, r/Calibre) + X keyword search produced the rest of the sheet: **319 rows, 161 UNANSWERED** (`question-sheet.csv` — columns: source, platform, startup, person, customer_type, problem, question, status, url, upvotes, comments). The exact phrasings below come from there.

## 3. Top 10 recurring questions (exact wording, source linked)

| # | Question (as asked) | Problem | Who asked | Source |
|---|---|---|---|---|
| Q1 | "i need a PDF to EPUB or MOBI converter that actually works. all the stuff i tried like Calibre or online converters just mess everything up, repeat page numbers, break paragraphs weird, fonts all over the place." | converter-quality | PDF owner | r/kindle `1sa7guk` |
| Q2 | "does it work with just pdf, docs or ppt or I can also give it a link of any lecture video on youtube?" (founder answered — so: answer it *better*, don't repeat it) | file-types | student | X reply under @leslie_rh7, @Contrarian03 `2099220509955383730` |
| Q3 | "I don't need/want an app. I just want to read on an ereader." + "Try transferring from Calibre to your Kindle by cable … (it's probably not working because of the DRM)" | delivery | e-reader owner | r/kindle comments |
| Q4 | "You find a book somewhere, download the EPUB somewhere else, open it in another app, and then your actual life…" (549↑) | fragmentation | PDF owner | r/ebooks `1w0op19` |
| Q5 | "Depends on the PDF. If it's a scan, you need a tool with really solid OCR, since smart reflowing is notoriously hard for those." + "very old scans that were pdfs and unavailable otherwise" | scans/OCR | PDF owner | r/kindle + r/Calibre |
| Q6 | "Are you by any chance implementing saving the file to .mobi?" + "How does it handle non-English scripts? Most of my pdfs are about academic texts about different languages and their histories" | formats | PDF owner | r/kindle `1sa7guk` + r/ebooks `1x39d2e` |
| Q7 | "good educational reading shouldn't have a financial barrier that steep" / "paying an exorbitant amount for digital licenses … to LEASE a book" | price | reader | r/ereader + r/ebooks |
| Q8 | "I have a book in PDF that I wanted to read on my Boox… It's perfectly capable of viewing PDFs" | delivery/reader | X reader | X `@alykhairy` |
| Q9 | "how would I clear all of the details on it? like to make it private?" + "We do digitize our own books… I have bad vision" | privacy + own-copy digitising | X / r/ereader | X `@socioxengineer`, r/ereader |
| Q10 | "If it's just text, you convert and manually clean up the mess that comes out in the epub" + competitor PureEPUB: "mid-sentence line breaks, OCR junk, mangled quotes" | cleanup | PDF owner / indie author | r/kindle `1wo017r` |

## 4. 30-day content plan (one piece per question, no product pitch)

Rules per playbook: answer the question *better than the startup did*, no link to our product in the body, tag the startup whose users benefit, and log every post with a `?s=` ref tag so `https://epub.ftak.net/stats` shows conversions per post.

| Day | Piece (question) | Format | Tag | Distribution beyond the post |
|---|---|---|---|---|
| 1 | Q1 "why my PDF looks broken on the Kindle" — 3 converters on the same PDF, screen recording of the broken output vs the clean one (repeated page numbers, split paragraphs) | 30s clip | @hyperknow_ai, @trypensive | reply in the r/kindle thread |
| 3 | Q2 "can it take PDF/DOCX/PPT, or a video link?" — live 30s: PDF + PPT + a YouTube link into a study agent, then the same file into a Kindle-ready EPUB | 30s clip | @hyperknow_ai (they take files; we make them a book) | reply to @Contrarian03 under @leslie_rh7's post |
| 5 | Q3 "get it on the device without Calibre" — free template: **Kindle/Kobo/Boox/Apple Books delivery checklist** (email-to-Kindle address, USB, Apple Books import) | free template | @Sinaidotai | post template, link from bio |
| 8 | Q4 "one file, one flow" — clip: PDF → EPUB → opens in Apple Books, Kindle, Kobo, Boox | 30s clip | @Plotsy_inc, @Sinaidotai | |
| 11 | Q5 "my book is a scan" — clip: 40-page camera scan → OCR → real EPUB with chapters → open on e-ink | 30s clip | @trypensive, @SpokenPress | DM the askers who said "old scans" |
| 14 | Q6 "MOBI? non-English?" — clip: same PDF → EPUB3, then show what Kindle/Apple Books/Kobo accept; show OCR on a Hindi/Japanese/Arabic page | 30s clip | @Sinaidotai | reply to @erikkmartins |
| 17 | Q7 "what does this actually cost" — **all-in price table of 5 converters** (free tier page limits, per-book cost, per-month cost, plus scan/OCR add-ons) | price comparison | @SpokenPress, @hyperknow_ai | drop in r/ebooks/r/kindle threads |
| 20 | Q8 "read it on my Boox/phone" — clip of the EPUB on a non-Kindle e-reader + phone | 30s clip | @Sinaidotai | |
| 23 | Q9 "keep it private" — free template: **local-first conversion + delete-after-read checklist** (no upload, what we do/don't keep) | free template | @LittlebirdAI, @trypensive | |
| 26 | Q10 "the output is a mess" — 30s clip: take a Calibre-mangled EPUB, show what it breaks (split paragraphs, repeated page numbers, OCR junk), then re-convert from the source PDF and show it clean. Tag PureEPUB if their KePub output does it better than ours | 30s clip | @SpokenPress, @Plotsy_inc | DM everyone who said "manually clean up the mess" |

Combo worth writing down (playbook step 2): **PDF → (OCR if scanned) → EPUB3 with TOC → send-to-Kindle / Apple Books / Kobo** is the real chain; our tool owns the middle two links, the device apps own the last. Every piece above is one link of that chain.

## 5. Step 3 — what to measure (after the 30 days)

- Ignore likes. **Bookmarks > likes** on a post = someone plans to come back → repeat that topic.
- Replies that contain a follow-up question beat reactions.
- Conversions per post via `?s=<post-tag>` in `https://epub.ftak.net/stats` (ref counts already exist in the app).
- Template downloads / EPUB Doctor runs = the intent signal that matters.
- Tag every topic with a customer type (student / indie author / e-reader owner / accessibility reader) so you can see which problems keep bringing in people you have not seen before.

## 6. Step 4 — the free tool (one small thing)

**Scan → EPUB on the phone, private** — a PWA at `epub.ftak.net/scan`: camera scans pages → EPUB with detected chapters + TOC → downloads straight to Files/Kindle. No account, no upload of the scan if it can run on-device, file deleted after.

Why this one, and not the obvious "EPUB fixer": a competitor already shipped the free local EPUB cleaner (PureEPUB, r/kindle `1wo017r` — clean EPUB for Kindle, KePub for Kobo, no accounts, everything wiped after conversion). Cloning it wins nothing. The unfilled hole the sheet shows is **scanned physical books**: old scans ("very old scans that were pdfs and unavailable otherwise"), books with no digital edition, accessibility readers ("We do digitize our own books… I have bad vision"), and the group already paying with time — not money. pdf2epub's OCR path is the only asset here that no free competitor claims end-to-end.

Rollout: link in bio, drop it in the Q5/Q9 threads and in the "what do you do with physical books that you wish you had ebooks of?" thread, DM every asker who mentioned a scan, an old book, or their own eyesight, then ask what they still cannot do with it.

## 7. Step 5 — the paid feature ($10/mo, 100 users, $1k MRR)

**Shelf — $10/mo**: the batch/library tier on top of the free scan tool.
- Unlimited re-runs and repairs of a converted book (fix OCR errors, re-split chapters, rebuild TOC)
- Batch queue: drop 50 scans (a shelf, a course, a research stack) → get 50 EPUBs
- Personal library index: all your books searchable, highlights + notes synced across Kindle/phone
- Email-to-EPUB ("mail me a PDF or a photo of a page, get the EPUB back") and one-click Send-to-Kindle delivery
- Priority queue + larger caps (the free tool's 200MB / 500-page limit becomes the paywall)

Who pays: accessibility readers and their households, students with a stack of textbook PDFs, book collectors, small libraries/labs — the people the sheet shows already paying in time.

Sequence: take the 20 heaviest scan-tool users, DM them price + two lines on what it does. **5 yes → build it. Fewer than 5 → the feature is wrong, the price is fine.**
100 × $10 = $1k MRR. Keep the free path free (one book, no signup) so the funnel does not close.

## 8. Risks / open items

- X reply mining under these founders is exhausted as a source (see §2). Do not spend more time there; the Reddit threads and X keyword search are where the questions live, and both are already in the sheet.
- Competitors visible in the sheet (all live, all free-or-cheap): **PureEPUB** (r/kindle `1wo017r`, 46↑/31c — local, no-account cleaner with device-specific output: EPUB for Kindle, KePub for Kobo), **Leaf & Spine** (reader app, free-lifetime promo), **TOMEIO** (r/ebooks `1w0op19`, 546↑/153c — "Stremio for books", attacking the fragmentation complaint), jumapps pdf2epub (Android), FreeReader, Xodo, Okular, Calibre. Any claim of "cleanest EPUB" must be true on a scanned page — that is the fight, and PureEPUB is the bar for reflow.
- Seed data caveats (in `seed_raises.csv`): Spoken is on the window edge and two trackers disagree ($500K Jan-2026 vs $1.0M Dec-2025); Plotsy conflicts (Jun 25 vs Aug 12); Docupath conflicts (Jul 8 vs Jul 23); Sinai.ai is labelled pre-seed by the company and "seed" by Tracxn.
- Before posting: the pdf2epub link must be on the X bio of whichever account posts, otherwise step 3 measurement is impossible.
