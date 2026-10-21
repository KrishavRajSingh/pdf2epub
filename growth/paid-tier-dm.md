# Step 5: the $10/mo paid tier, ready to run

## The offer (one sentence per line, this is what the DM says)
- **1,000 scanned pages a month, included.** No credits, no page maths, no account limits.
- **Batch**: drop 50 scans, get 50 EPUBs back.
- **Repair**: re-run and fix a conversion as many times as you want (OCR typos, chapter splits, TOC).
- **Send-to-Kindle delivery**: the finished EPUB goes to your Kindle address, automatically.
- **Nothing stored**: files are processed in memory and deleted, same as the free tier.
- $10/mo. No annual plan, cancel whenever.

Why 1,000 pages: convert2epub sells 1,000 credits for $11, which is 1,000 OCR pages. $10 for the same
volume, with batch and repair included, is the comparison to beat.

## Who pays (from the harvested data)
- Accessibility readers and households: they digitise their own books, no digital edition exists, and
  they pay in time today. The sheet quotes them: "We do digitize our own books... I have bad vision".
- Students with a stack of textbook PDFs: the 500-page, 200MB files.
- Book collectors with physical books that were never digitised.
- Small libraries and labs.

## The DM (short, two lines of what it does, then the price, then one question)
Subject: you asked about scanned books

> Hi, you asked about turning scanned books into a real EPUB with chapters. I built a free tool for
> that (epub.ftak.net) and it does one book at a time, no signup, nothing stored.
>
> I am adding a $10/month tier for the people doing this at volume: 1,000 scanned pages included,
> batch conversion of a whole shelf, and the finished file sent straight to your Kindle.
>
> Worth a try, or is one book at a time enough for you?
>
> Krishav

Variants to A/B (one variable each):
- lead with the batch instead of the pages
- lead with "your file never leaves the server" instead of the price
- ask "how many books do you have left to convert?" instead of "worth a try"

## Kill criteria (from the playbook)
- DM the 20 heaviest users (most conversions, or most scans).
- 5 yes -> build it.
- Fewer than 5 yes -> the feature is wrong, the price is fine. Change the feature, not the price.

## What has to exist first
1. The email capture on the landing page (done, shipped in `603efed`). Every conversion with an
   email lands in `conversions.log` as `{"email": ...}`.
2. The list to pick the 20 from. Export with:
   `grep -o '"email": "[^"]*"' conversions.log | sort -u`
   (on Railway the log is on the volume at /data, so read it with `railway shell` or the volume
   browser). Nothing else stores it, which is also why it must not sit on a host that wipes disks.
3. A way to tell the heaviest users apart: the log has `pages` per conversion, so the heaviest are the
   ones converting 300+ page scans.

## Do not do yet
- No Stripe, no accounts, no dashboard until 5 people say yes. Charging before that is how the free
  funnel dies.
- Do not move the free tier behind a signup. The whole funnel is "no signup, no paywall", and that
  is the line in the sand against freepub.app and pureepub.com.
