# growth/ — customer-first playbook run for pdf2epub

Files
- `seed_raises.csv` — 20 seed-stage startups announced 2026-01-20 → 2026-07-20 (3–9 months before 2026-10-20), with amount, date, customer, founder handle, source URL, and data caveats. 5 of them sell to the same customer as pdf2epub (marked in `content-plan.md` §1).
- `question-sheet.csv` — 319 real questions from X + Reddit (r/ebooks, r/kindle, r/ereader, r/Calibre). Columns: `source, platform, startup, person, customer_type, problem, question, cluster, status, url, thread, upvotes, comments`. `status` = UNANSWERED / answered / answered by founder / open.
- `competitive-pricing.md` — 5 alternatives + us priced for one 300-page scan, checked 2026-10-20 (convert2epub charges $0.011/page for OCR; freepub.app and pureepub.com own the free lane).
- `reply-pack.md` — 11 Reddit targets with rules, drafts and `?s=` tags. 5 of those comments are live (2026-10-20).
- `reddit-post-redo.md` — the r/ebooks post rebuilt on the pattern of the 314↑ competitor post.
- `new-product-options.md` — net-new product candidates scored from the same data (A Shelf / B delivery client / C lease-free library / D instructor intake).
- `content-plan.md` — the 5 picked startups, top-10 questions with exact wording, the 30-day content plan with tag targets, measurement rules, the free tool, the paid feature, and the open risks.

Re-run the harvest (needs `twitter` and `rdt` CLIs authenticated; X reads use the brand Chrome profile)
```
python3 scripts/harvest.py leslie_rh7 yi1inz hyperknow_ai ahmadKaamel Sinaidotai \
                        yoonseok_yang trypensive alapshah1 LittlebirdAI SpokenPress
python3 scripts/reddit_harvest.py ebooks kindle ereader Calibre
python3 scripts/merge_sheet.py     # rebuilds question-sheet.csv from all sources
```
Notes
- `scripts/harvest.py` caches every fetched thread under `replies/`, so re-runs only fetch what is missing. Use workers=2 — the X API 429s hard above that.
- `scripts/extract2.py` prints the strict product-question view of the founder threads (used for the §2 finding).
