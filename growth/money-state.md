# Money state — can the current version make money?

Updated 2026-10-22. Answers: **yes**, but the current version was leaking the buyer in four
places. All four are fixed in the commits below and land with the next deploy.

## The evidence that it can

One browser session on 2026-10-21 converted **68 PDFs / 12,908 pages in 32 minutes**
(11:47–12:09 UTC), ~190 pages per file, and hit the 500-page cap **7 times** with files of
528–570 pages / 10–38 MB. That is a textbook-library owner, not a casual user. That is exactly
the Shelf customer: 1,000 pages/month for $10.

Source of that traffic: `?utm_source=substack&utm_medium=email` — the **deepculture** newsletter
issue #243 (26,000 subscribers, 35% CTR, published Oct 20) put epub.ftak.net in its Bonus slot.
Every other channel produced nothing: `?s=hn` sent 875 visits and **0** conversions, Reddit posts
1 and 0 upvotes.

deepculture is a third-party newsletter, not ours (checked 2026-10-22: it features other people's
products in the same slot — kooler.me, bigwords.page, playtakt.app — and Krishav's own
"Japan/Singapore" curated line is a retweet he posted on X, not deepculture copy; the deepculture
feed contains no such line). So the lever is not "email our list", it is **buy the slot**: the
Bonus slot is sold as a Classified Ad, and one placement produced 68 conversions in 32 minutes.
Check `https://www.passionfroot.me/deepculture` for the rate.

## What was broken (all fixed)

| # | Leak | Was | Now |
|---|---|---|---|
| 1 | Checkout link in `reddit-posts.md` | `...WupgVW4...` → **404** | one link, `...WupgYW4...`, verified 200 |
| 2 | Fulfilment email had no pay link | "$10/month" and no URL | links `/shelf` |
| 3 | Cap rejection showed raw JSON | `{"detail":"over 500 pages in v1"}` | `err_page` + in-page `PITCH` with mail + subscribe |
| 4 | Paid tier unreachable from the site | no route, no link | `/shelf` page, linked from the landing page and the sitemap |

Plus the thing that was missing entirely: **email capture at the moment of intent.**
`/lead` (POST email, reason) logs the address, and the cap-rejection panel asks for it. Before
this, 82 conversions produced **0 emails** — the field was optional and worded as a footnote.

## Now measurable

`/stats` gained three numbers, because the money leak was invisible until now:
- `leads` — emails captured via `/lead`
- `cap_rejects` — requests that hit the 200MB / 500-page cap (the intent signal)
- `checkouts` — `/thanks` hits carrying a Polar `checkout_id` (money)

Also `refs` now shows `shelf` and `thanks` separately, so a newsletter link to `/shelf` is
attributable.

## The pricing position (unchanged, still correct)

`growth/paid-tier-dm.md` has the comp: convert2epub sells 1,000 OCR credits for $11. Shelf is
$10 for 1,000 pages plus batch conversion and Kindle delivery. Same volume, cheaper, and the
difference is the output quality (real chapters, real paragraphs).

## What is still missing to make the first sale

1. **The deploy.** Every fix above is in git and waiting on Railway (builds paused platform-wide
   since Oct 20, security-incident related). The watcher will deploy it.
2. **A published pay link.** `/shelf` exists now, but nothing points at it from outside:
   - the deepculture issue #243 already linked `epub.ftak.net` and produced 68 conversions —
     **it never mentioned a paid tier.** The next issue should link `/shelf` directly.
   - Reddit/X posts point at the free tool. One of them should point at `/shelf`.
3. **The deepculture slot, again.** Issue #243 shipped one free-tool link and 68 conversions
   came. The slot is sold (Classified Ad) — the next issue can carry the same link pointing at
   `/shelf` instead of `/`. That is the only channel with proven conversion volume, and it is
   repeatable for the cost of one slot. Ask for the rate; a Classified Ad is far cheaper than the
   $10/mo a single Shelf subscriber pays.
4. **The throttle must not cut a shelf owner.** The pending build keys the throttle on the real
   client IP. At 10/min and 30/day it would have 429'd the 68-in-32-minutes burst at file 31 —
   more than half the revenue event. Now 30/min and 300/day.
5. **fulfil.py must not answer the bank.** Its query was any PDF attachment, so a bank statement
   or broker alert from anyone would have been converted to EPUB and mailed back with a $10 pitch.
   It now only acts on mail that reads like a request.

## The rule for the free path

The free converter stays free and un-walled (see `PRODUCT.md`). The pitch appears only where the
free path has already failed the user: the cap rejection, the fulfilment email, and `/shelf`.
Never a signup, never a paywall, never a modal.

## The product decision (2026-10-22)

**Free stays at 500 pages per file. On purpose.** The 7 cap rejections were books of 528–570
pages, just over the line. Raising the free cap to 600 would convert all 7 and let the one buyer
we have convert all 68 of their books free, forever, and never pay for anything. **One book free,
a shelf paid** is the only line that sells.

**Shelf is $10/mo for 1,000 pages, no per-file ceiling.** The ceiling is the product: the free
tier stops at 500 pages, which is exactly where a textbook sits. Shelf goes to 2,000 pages per
file and 500MB, so the big ones go through. Priced at parity with convert2epub ($11 per 1,000
OCR credits) but the buyer gets their 564-page books converted instead of doing it in Calibre
themselves. Their time is the currency.

**How a subscriber gets access: a key, not an account.** No accounts, no database, no signup:
- Polar redirects to `/thanks?checkout_id=polar_c_xxx`
- a real checkout id mints a key, one key per checkout, written to `shelf-keys.txt` on the volume
- the key goes in the url: `epub.ftak.net/?k=KEY`, and it lifts the ceiling on `/convert`
- a junk checkout id mints nothing; a junk key lifts nothing

**The key has to reach the buyer, or they have paid for nothing.** Two paths, both live:
- `/thanks` shows the key on the page
- `scripts/keys.py grant <email>` emails it (verified end-to-end: mail sent, body correct)

**A lead has to be chased.** Someone who types an email into the cap-rejection box is a buyer we
would otherwise never reach. `scripts/keys.py leads` pulls lead lines off the railway log and
emails them an offer; `scripts/keys.py watch` runs it every 5 minutes. Run it as a background job.

### What is still not true

- **Batch conversion is not built.** `/convert` takes one file. The offer says "send me a shelf
  and I will convert it" — that path is the manual one (`scripts/fulfil.py`), which is real, but
  it is not a product feature. Do not sell batch until `/convert` takes many files.
- **Kindle delivery is not built.** The offer says the EPUB is sent to the reader's Kindle
  address. Today the fulfilment email says "send it to your Kindle with the subject line convert",
  which is the manual instruction. Either build the delivery or soften the wording.
- **1,000 pages a month is not metered.** The key lifts the ceiling; nothing counts pages. Until
  there is a counter, honour it by hand: `growth/leads.csv` plus the conversion log.

### The channel that works, and it is not Reddit

deepculture issue #243 put epub.ftak.net in the Bonus slot and produced 68 conversions in 32
minutes from one reader. That slot is sold (Classified Ad, see passionfroot.me/deepculture) and it
is repeatable for the cost of one slot. **The next issue should link `/shelf`, not `/`.** Reddit
posts got 1 and 0 upvotes; the HN post got 875 visits and 0 conversions.

## The wait (Railway outage, from 2026-10-20)

Railway paused all builds platform-wide and then disclosed a security incident: an unauthorized
third party accessed encrypted environment variables and may have decrypted some of them. Builds
and deployments are frozen while they rotate credentials. Their own notice: rotate your env vars
and registry credentials, review your logs.

**Our exposure from the breach: none.** The pdf2epub service has exactly two env vars
(`LOG_DIR=/data`, `PORT=8000`), neither a secret, so there is nothing to rotate. No tokens in
git history or the working tree. Polar, GitHub and Gmail are separate accounts.

**The live build keeps serving through the pause** (visits and conversions are still ticking,
volume data intact). Nothing is lost, but every fix is stuck behind the freeze.

**Three loops are running on the Mac and will do the work the moment the freeze lifts:**

| loop | what it does | when it fires |
|---|---|---|
| `scripts/railway_deploy_watch.sh` | retries `railway redeploy --from-source` every 60s, then verifies `robots.txt` + `/health` | the instant builds reopen |
| `scripts/fulfil.py --watch` | converts any PDF that arrives by email and emails the EPUB back | every 60s, and it needs no deploy |
| `scripts/keys.py watch` | pulls leads off the railway log and emails them an offer | every 5 min, and it needs no deploy |

Note the CLI session expires and auto-refreshes; the watcher retries on `Unauthorized` rather
than pretending a deploy happened. That was one of three watcher bugs fixed (the other two: a
missed `"Unauthorized"` branch that made it burn 20 minutes per attempt, and a case-sensitive
match on Railway's capitalised `"Paused temporarily"`).

**Do not buy the deepculture slot until the deploy lands.** The slot links to `/shelf`, and
`/shelf` is a 404 until the freeze lifts. A paid placement pointing at a 404 is a wasted slot.

**While waiting, the two things that pay out without a deploy:**
- `fulfil.py` is live on the Mac. Someone who emails a PDF gets an EPUB back today, with the
  Shelf offer in the email.
- `keys.py grant <email>` mints a key and emails it, pushing it to the railway volume over
  SFTP so the live site accepts it.
