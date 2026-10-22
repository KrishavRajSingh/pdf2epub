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
