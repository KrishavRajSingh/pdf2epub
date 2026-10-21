# New-product options (from the same harvest, not a new brainstorm)

Inputs: the 20 seed raises (who got funded Jan–Jul 2026 = demand signal), the 319-row question sheet (223 open rows), and pdf2epub's existing distribution (epub.ftak.net + `?s=` refs + /stats).

## Where the money went in the last 9 months (read the seed list as a demand map)
- **AI for students/instructors**: Hyperknow $1M (students pay $0/$18/$50 per user/mo), Pensive $6.8M (instructors buy grading back).
- **Document ingestion for back offices**: Cifrato $1M, Docupath $3M, Rely $4.5M, Structured AI $4.2M, Factify $73M.
- **Accessibility**: OOrion €1M, WillShine (blind/low-vision students).
- **Book/audio formats**: Spoken, Sinai.ai, Voxa, Plotsy, Bindery, READO.
Price anchors for the $10/mo target: $18–$50/mo for AI study tools, $20/mo for a productivity AI, per-title pricing for audiobook production.

## Open-row counts in the sheet (223 open rows)
| Pain | Open rows | Note |
|---|---|---|
| DRM / leases / "I don't want to lease a book" | 18 | biggest single friction |
| "I don't want an app, I want to read on my e-reader/phone" | 12 | device-delivery |
| speed / size / caps ("how long did it take", "file too big") | 10 | |
| library fragmentation / highlight+note sync | 4 | high-engagement thread (546↑) |
| batch / "all my books" | 4 | |
| own physical books with no digital edition (digitise yourself) | 3 | accessibility + collectors |
| non-English scripts | 2 | |

## The four candidates

**A. Shelf — batch digitising + personal library (own-books crowd)**
Convert a stack of physical books (phone scan → OCR → EPUB with detected chapters), keep a searchable index, sync highlights. Payer: accessibility readers, collectors, small libraries. $10/mo = 100 books/mo + repair bench + email-to-EPUB. Signal: 2 of the 20 funded startups serve blind/low-vision users; our sheet shows them paying in time, not money. Risk: OCR quality is the whole product; our 200MB/500-page cap is the ceiling. Kill test: 10 DMs to the "I digitize my own books" askers, 3 say yes.

**B. No-app delivery client (the 12 "I just want to read on my device" rows)**
Convert anywhere → the file lands on Kindle/Kobo/Boox/Apple Books automatically (watch folder, email-in, Send-to-Kindle address). Free: 3 books/mo. $10/mo: unlimited + library sync + annotations. Distribution: reply in exactly the threads the sheet cites; demo is a 30s clip. Risk: Apple Books/Kindle APIs are hostile, Send-to-Kindle is a weak moat.

**C. Lease-free personal library (the 18 DRM rows)**
Ingest only what the user owns, keep one highlight/note store across devices, re-encode to EPUB for personal reading. $10/mo. Risk: adjacency to DRM circumvention — keep the framing strictly "your own files", legal review before building, don't lead with it.

**D. Instructor/analyst document intake (email-to-EPUB)**
"Mail me a syllabus/textbook PDF → get a clean, chaptered EPUB + study handout." Payer: instructors, coaches, research groups. $10/mo × 100 = 100 instructors, and instructors are proven payers (Pensive). Signal: 5 of the 20 funded startups are document-ingestion companies. Risk: needs a sales motion, not just content.

## Recommendation
Keep pdf2epub as the **distribution wedge** (it has a live site, attribution loop and a working Reddit presence) and take the new product from the strongest signal above:
- **A (Shelf)** if you want the biggest emotional pull and the OCR moat nobody claims end-to-end (PureEPUB does reflow, not camera OCR).
- **B (delivery client)** if you want the fastest to ship (it is the answer to the most-asked question) and the least new code.
- **D** only if you are willing to do sales; content alone will not get 100 instructors to $10/mo.

Drop **C** unless legal clears it.

## What a genuinely net-new vertical run would look like
Same machinery (research → harvest → cluster → content → free tool → paid tier), different seed set: pick one vertical (e.g. legal document review, clinical notes, logistics paperwork), pull that vertical's 20 seed startups + their communities' unanswered questions, and run the identical funnel. Cost: one fresh research pass + one harvest of a different subreddit set, roughly the same wall-clock as this run.
