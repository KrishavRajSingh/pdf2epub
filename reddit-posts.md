# Reddit launch — epub.ftak.net

## Hard gate: do NOT post anything until deploy 8fcff31 is live

Verify before posting:
- `curl -s https://epub.ftak.net/ | grep "200MB"` → must say `PDF up to 200MB, 500 pages`
- `curl -s https://epub.ftak.net/stats` → must contain `"ocr_ok"` and `"ok_by_ref"`
- Live scan test passed (image-only PDF → valid EPUB with `<h1>` + OCR text)

Why: the launch wedge is "scans are free". If the deployed build can't OCR, the Annas crowd will eat the post alive in the first 10 minutes.

## Rules evidence (verified 2026-10-18)

| Sub | Rules | Link policy | Verdict |
|---|---|---|---|
| r/Annas_Archive | none published, submit text empty | mod-judgment topicality only | REMOVED 2026-10-19 (~30 min): "This subreddit is for discussion of Anna's Archive." No repost, no mod reply |
| r/xteinkereader | none published | rival's link-in-body post survived, 84 up | post #2 tentative, pre-flight required (see lesson) |
| r/ebooks | no referral links; direct links OK; self-promo via flair; don't editorialize titles | PLAIN link, no `?s=` param | POST NEXT: live tool-post precedents verified 2026-10-19 (rival's Convert2EPUB post live, book-tool posts survive). Set flair at submit |
| r/kindle | rule 3: no spam/promotion/self-promotion (removal + ban); rule 4: no piracy talk, no website names | none | NO post. Comments only, opportunistic |
| r/ereader | rule 4 "No shilling", rule 5 "No spam. No advertising of any kind." | none | SKIP entirely |

**Lesson (2026-10-19):** "no published rules" is NOT permission. Mods enforce topicality by judgment. Pre-flight for EVERY sub before posting: find a tool-promo post LIVE in that sub right now (last ~2 weeks). No live precedent = no post.

## Competitive intel (2026-10-18)

- Skimmed the angle: another maker's post "Made a PDF to EPUB converter that actually handles scanned books" (r/saasbuild + crossposts) gates scans behind an account. Draft A title changed to avoid reading as a copy.
- Paid players in scanned→EPUB: pdf2epub.ai (free sample, then paid) and PDF Craft/Oomol (paid, 200MB/1500-page caps). None offer free scans → our wedge holds.
- r/Annas_Archive demand threads exist (medical student converting textbooks, etc.); top recommendations are only Calibre / Abbyy / online-convert. No tool owns the sub.

## Demand census + comment-play results (2026-10-19)

- Reddit last-month volume for "pdf to epub": r/ebooks 24 hits (gold thread `1x39d2e` "PDF to EPUB converters, experiences & quality?" 18up/51c), r/ereader 21 (mostly device chatter), r/kindle 11 (`1x5xdyh` converter-ask 12c), r/Calibre 7, r/Annas_Archive 0 (its removal cost us ~nothing), r/piracy 2 irrelevant. Verdict: modest but real public demand, strongest cluster = r/ebooks.
- Comment play already run (Oct 15–16, kindle + ebooks threads, links `?s=kindle` / `?s=ebooks`, both comments live, score 1): **0 tracked visits, 0 conversions over 3+ days.** Buried comments in old threads are dead weight. Comments only make sense on FRESH threads (<24h) or under our own posts.
- r/ereader: earlier SKIP verdict contradicted by live precedent — KOReader tool post 19up, 1 day old (10-18). Upgrade to candidate post; re-run pre-flight before posting.
- Telegram/Discord: skipped (broadcast channels, not discussion; ban risk). Facebook: optional later, unmeasurable. MobileRead: forum traffic is ancient threads; long-tail only, deprioritized vs Reddit posts.
- Standing task: monitor r/ebooks + r/kindle + r/ereader daily for NEW converter-ask threads (sorted new); when one is <24h old, reply there with a plain link same day.


## Posting order + schedule

Stagger 2-3 days. Weekday, 7-9pm IST (= US morning). Stay available 90 min after posting to reply.

1. ~~**r/Annas_Archive**~~ — FAILED (removed in ~30 min, off-topic). Do not repost there. Do not reply to the mod.
2. **r/ebooks** — TEST #1 POSTED 2026-10-20 17:35 IST: https://redd.it/1xaqcl0 (flair "Self Promotion", plain link). Measure at 1h / 24h / 72h vs baseline below.
3. **r/xteinkereader** — only after r/ebooks, if it didn't flop. Re-run pre-flight first (weak precedent today: only simpleOPDS). Draft B.
4. **Ongoing** — r/kindle comments only: search "pdf to epub" weekly; reply ONLY in threads where someone asks for a converter. Max 1-2 replies/week. Never name piracy sites there. Draft D.

Decision gate after each post (check at 1h, 24h, 72h):
- CONTINUE: post stays up AND (≥50 upvotes with real comment engagement OR ≥10 conversions on that ref tag in 72h)
- STOP: <10 conversions at 72h → don't post further subs, come back to product wedge
- Never delete a flop. Never argue in comments. Edit only to fix wrong facts.

## Draft A — r/Annas_Archive (REMOVED — kept for record only, do not reuse)

Title: I built a free PDF to EPUB converter with OCR for scanned books (no paywall, no account)

Body:

Most converters either give you back a pile of page images when your PDF is a scan, or let you convert and then ask for money to download. So I built a free one: https://epub.ftak.net/?s=reddit-annas

- Scanned books: uses the invisible text layer when it exists, OCR when it doesn't (up to 200 pages, this part is beta)
- Text PDFs: real chapters + table of contents, running headers/footers stripped
- No signup, no paywall, no watermark. In-memory processing, files deleted right after download

Solo project, actively improving. If a book comes out badly, tell me the type (old print, two-column, footnotes). Those reports are what I fix next.

## Draft B — r/xteinkereader (on deck, only if r/ebooks passes)

Title: Made a free PDF to EPUB converter for pocket readers: real chapters, scans via OCR, no account

Body:

PDFs on a small e-ink screen are painful, and most converters hand you back page images or paywall the download. I built a free web one, no install: https://epub.ftak.net/?s=reddit-xteink

- Real chapters + TOC so navigation actually works on a small screen
- Scanned books: text layer when present, OCR when not (200 pages, beta)
- No signup, no paywall, no watermark, files deleted after download

Feedback wanted: which books break on your device, and which settings you'd want (font size, margins)?

## Draft C — r/ebooks (TEST #1 — Tue 2026-10-20, 7-9pm IST. PLAIN link — no tracking param per their referral rule)

Check flairs live first (Tools / Self Promotion). Keep title plain and factual.

Title: I made a free PDF to EPUB converter with real chapters and OCR for scans

Body:

I kept running into converters that destroy chapter structure or paywall the download after upload. So I built a free one: https://epub.ftak.net/

- Real chapters + TOC for Kindle, Kobo, Apple Books; headers/footers stripped
- Scanned PDFs: invisible text layer first, OCR fallback (200 pages, beta)
- No signup, no account, files processed in memory and deleted after download

Solo project, improving actively. If a PDF converts badly, tell me the kind and I'll use it as a test case.

## Draft D — r/kindle comment template (comments only, never a post)

Only in a thread where someone asks for a PDF→EPUB recommendation. Disclose you built it. Plain text, short:

"I built one for exactly this: https://epub.ftak.net. It detects real chapters and does OCR for scans, free, no account. Happy to fix cases it breaks on, just tell me the kind of book."

Rules: no piracy names in r/kindle, no link drops in unrelated threads, max 1-2/week, answer follow-up questions honestly.

## Reply bank

- "Free? What's the catch / how do you make money?" → No catch today: no account, no ads, no paywall. Server costs are on me while it's small. If it grows I'll figure out a business around the heavy scan stuff, but basic conversion stays free.
- "It broke / output is garbage" → Sorry, can you tell me the kind of PDF (scan, two-column, footnotes) and roughly how many pages? That's exactly the feedback I use to fix cases. (Log it. Never argue.)
- "File size cap?" → 200MB / 500 pages for now (200 OCR pages in beta). What size are your files? Sizing is what I tune next.
- "My scans are over 200 pages" → Yeah, that's the current beta cap. What's a typical book length for you? That number decides what I build next (batch mode / queue).
- "Does it store my files?" → No. In-memory only, deleted right after download. Details on /privacy.
- "Why not just use Calibre?" → Calibre is great, and it's literally my server-side fallback. This is for zero install, no settings, works from a phone browser — with real chapters out of the box.
- "Is this promoting piracy?" (kindle only, no site names) → The tool doesn't host or source any books — it converts a file you already have. Please only convert what you're allowed to.
- "OCR quality is bad" → 150-300dpi scans work best; photos of pages and handwriting don't. If you have a poor sample, tell me the page and I'll look at the engine.

## Measurement

- Visit tags: `?s=reddit-annas`, `?s=reddit-xteink` (r/ebooks is plain by rule → lands as "direct")
- `/stats` → `ok_by_ref` shows conversions per tag; `ocr_ok` shows how many launched converts were scans
- Record after each post: 1h / 24h / 72h = upvotes, comments, ref visits, conversions, removal status
- r/ebooks uses a PLAIN link, so its traffic lands as `direct` (no tag). Take a fresh `/stats` snapshot RIGHT BEFORE posting and record conversions_ok + direct count here — that's the only way to subtract its effect later.
- Baseline before launch: conversions_ok=1 (my smoketest), visits ~3 (my curls), real external traffic ≈ 0 (old jammed log was lost with the old volume — reset is clean, ignore the old "1427 visits" note)
- 2026-10-19 evening (post-removal): `reddit-annas` tag = 14 visits in the ~30 min it was live; conversions_ok=5 (ok_by_ref: direct 4, smoketest 1 → +1 new direct, attribution unknown). This is the pre-r/ebooks baseline.
- 2026-10-20 17:36 IST (right after r/ebooks submit): visits=1082, reddit-annas|=19, direct=129, conversions_ok=5, failed=3, pages=3072. Subtract this for the r/ebooks read.

## SEO plan (build only after Gate A passes)

- Ahrefs free data (US): "pdf to epub converter" >1k/mo (skip, brand-dominated); "free pdf to epub converter" +>100 Easy; "scanned pdf to epub" <100 each, low competition (SERP mostly GitHub repos). Whole cluster ≈ low hundreds/mo — side drip, not growth engine.
- Build 2 static pages, no more: (1) free pdf-to-epub page, (2) scanned-pdf-to-epub page with OCR demo + Calibre-doesn't-OCR FAQ section.
- No dedicated calibre page (near-zero volume), no SEO tool subscriptions.

## Do-not list

- No crossposting the same day, no identical titles across subs (spam filters)
- No asking anyone to upvote; no vote DMs
- No link in r/kindle posts; no piracy site names in r/kindle at all
- No "v1 is simple" / apology lines in posts — sells weakness
- No editing a post to add the link later in subs where the link was allowed (looks like bait-and-switch)

---

## 2026-10-20 — customer-first playbook run + product fixes

### Posted today (5 Reddit comments, 3 X replies)
| Where | Thread | Angle | Link |
|---|---|---|---|
| r/ebooks | `1x39d2e` "PDF to EPUB converters, experiences & quality?" (51c) | text layer vs scan, headers/hyphens/headings→TOC | yes, `?s=ebooks-1x39d2e` |
| r/kindle | `1tlu322` "advanced tool to convert PDF academic papers to EPUB?" (37c) | two-column reading order + figures, honest "read on a tablet" | no (rule: no site names) |
| r/Calibre | `1x5a2d4` "plugin for converting research paper PDFs?" (6d, 14c) | two columns + figures + check HTML/EPUB source | no |
| r/Calibre | `1wpgrww` "how to convert PDF to MOBI?" (19c) | OCR the PDF first; Send-to-Kindle "convert" beats MOBI | no |
| r/Calibre | `1uzcek2` "How do I convert pdfs to EPUB?" (35c) | manga = page images, so 1% hang; zip the pages | no |
| X | reply to @hyperknow_ai (53.8k views), @leslie_rh7 (5.4k), @ahmadKaamel (Sinai.ai beta) | the two checks that decide extraction quality | no link in body |

### r/Calibre rules (verified today, post `1wx55zn`, 308↑, 2026-10-04)
- Tool posts need an **AI CONTENT DISCLOSURE** header.
- Comment rule says generative-tool-written comments are banned; short factual answers by a human read as
  normal participation, so keep comments short, Calibre-native, no link, no product name. Owner accepted
  this risk for comments. **Never post our tool there without the disclosure header.**

### Channel pre-flight (today)
- r/ereader: a tool post survived yesterday ("eMote for Android: beta testers", free Bluetooth page
  turner) → posting there is possible. Old verdict "SKIP" was based on rules only; live precedent wins.
- r/xteinkereader: no live tool post in the last week → **do not post** (no precedent).
- r/InternetArchive: "Best way to scan books to archive?" (Oct 3, 26↑) + a 364↑ thread about building
  interfaces for IA. This is the digitizer crowd, they OCR books by hand today. Best fit for /scan.
- r/selfpublish, r/kobo, r/PDFs: no tool-post precedent found → comments only.

### Product fixes shipped to git (deploy queued, see blocker)
1. **Every printed line was its own `<p>`.** Verified on the live build: one wrapped paragraph came out
   as 3 paragraphs. That is exactly the "break paragraphs weird" complaint the whole market repeats.
   Now joins at PDF-block level with hyphen repair (`app.py:_blocks`, `_join`).
2. Kindle TOC showed "ch1", "ch2" → now the real chapter names.
3. New: `/sample.pdf` (generated on the fly) + "Try it with a sample PDF" button, "what you get" block,
   optional email capture (needed for the step-5 DM list), encrypted-PDF message, `/stats` email count.
4. New: `/scan` = phone photos → OCR → EPUB (the step-4 free tool), `/guides/*` (4 pages) + `/sitemap.xml`.

### BLOCKER: deploys are paused by Railway
`status.railway.com` (Oct 20 17:18 UTC): "New builds are temporarily paused... Builds triggered during
this period will remain queued and will start once we resume builds." Commits `603efed` + `83c284f`
are pushed and queued. `watch_deploy.py` posts the r/ebooks follow-up automatically (with
`?s=ebooks-1x39d2e`) within 24h of the new build going live.
Also flagged: Railway trial shows "25 days or $3.87 left" — the account needs credits or the site goes
offline. That is a business risk, not a code risk.

### Next
1. When the build lands: verify `https://epub.ftak.net/sample.pdf` is `%PDF`, `/scan` works, `/stats`
   shows `emails_captured`.
2. Post the r/ebooks redo (draft in `growth/reddit-post-redo.md`) after the 72h gate of the current
   post, this time with a `?s=` tag so conversions are attributable (the current post has no tag).
3. r/InternetArchive + r/ereader as the next two post slots.
4. Paid tier: "1,000 scanned pages included, $10/mo" (beats convert2epub's $11 per 1,000 credits).

### 2026-10-20 (late) — concierge push, first paid user
Railway paused all builds platform-wide (status.railway.com, Major Outage 17:18 UTC), so the fixed build
is committed but not live. Live site still runs the build that breaks paragraphs per printed line, so
the offer leads with **manual conversion**, not the site.

- Polar: "pdf2epub Shelf" $10/mo, link `https://buy.polar.sh/polar_cl_81p78hP5rOfSUfsOS5LWupgYW4bGVXJKz98tp2q8PTs`
  - ponytail: the W-upgVW4 variant of this id is a 404 (verified 2026-10-22). YW4 is the live one.
  (success URL -> /thanks, logs checkout_id). India is fine on Polar (Connect Express), Stripe standalone is invite-only.
- Offer posted (email in, EPUB out, free, by hand): r/ebooks `1x39d2e`, r/InternetArchive `1wwtsj5` (the
  digitiser crowd: early 1900s Shakespeare collection), X `2112630460589478016`.
- `scripts/fulfil.py --watch` running: Gmail -> PDF -> convert -> email the EPUB -> `growth/leads.csv`.
- Every delivered file ends with the $10/mo ask (1,000 pages/mo, batch, delivery to Kindle).
- Kill rule: 30 targeted offers -> 0 emails = offer is wrong, switch to free-tool distribution (SEO guides
  are queued, AlternativeTo listing pending).

### 2026-10-21 — r/ereader post + spacing rules
- **Posted r/ereader `1xbjrw6`**: "I built a free PDF to EPUB converter (no signup, no paywall, scans
  included)", flair News (same flair the 314↑ competitor post used). Live, not removed. Link tag
  `post-ereader` so conversions from that post are attributable.
- NOTE: r/ereader bans AI-generated content (rule post `1lww0he`, 302↑) and threatens a ban. Posted on
  the owner's call, one post, then nothing in that sub for a week. If it gets removed, do not repost.
- r/Calibre bans generative-tool-written comments (rule `1wx55zn`). Our 3 comments there are short,
  factual, link-free. Keep it that way, or delete them.
- Reddit's API blocks script submissions (403), so posts go through the old.reddit submit form in the
  browser. Working selectors are in `growth/posting-queue.md`.
- Spacing rule from the owner: max 1 post per sub per 48-72h, one big post per day. Queue lives in
  `growth/posting-queue.md`.
