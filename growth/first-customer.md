# Getting customer #1 without paying for hosting

Constraint: no Railway credits until someone pays. Railway trial has **$3.86 left and 25 days**,
burning about $0.01/hour at current traffic, so the site survives a while on its own. The build
queue is a separate problem (Railway paused all builds platform-wide, 2026-10-20) and it resolves
itself.

## STATUS (2026-10-20, live now)
- Polar product **"pdf2epub Shelf" $10/mo** created in the `pdf2epub` org (India works: Polar pays out via
  Stripe Connect Express, Stripe standalone is invite-only in India).
- Checkout link: `https://buy.polar.sh/polar_cl_1jZLYsY7lODWs2QOnhNALMww3O7if69LL4nRQ1JiNmJ`
- Success URL -> `https://epub.ftak.net/thanks?checkout_id={CHECKOUT_ID}` (new `/thanks` route logs the
  checkout id, so we know which link converted; queued for deploy).
- Fulfilment loop: `scripts/fulfil.py --watch` (running) reads Gmail for PDF attachments, converts with
  the fixed pipeline, emails the EPUB back, logs every lead to `growth/leads.csv`.
- Offer posted: r/ebooks `1x39d2e`, r/InternetArchive `1wwtsj5`, X `2112630460589478016`.
- Warm thread list for the next posts: `growth/warm-targets.csv` (18 threads, ranked by comments).

## The cheapest path to a first customer: convert it yourself
The fixed pipeline is on this Mac right now. `scripts/manual_convert.py` uses the same code the site
uses, so a manual conversion costs **zero** hosting and produces the same fixed EPUB.

```
python3 scripts/manual_convert.py their-book.pdf --title "Their Book"
# -> mode: text | chapters: 12  headings: 12  paragraphs: 210
# -> wrote their-book.epub
```

So: find someone with a PDF that hurts, convert it for them, hand them the EPUB, keep their email.
That is the concierge version of the product and it is how you learn what people actually want
before you pay for a server. Every one of those conversions is a potential $10/mo subscriber, and
each one tells you the file type, page count and pain point to put in the paid tier pitch.

## Where to offer it today (no build needed, no hosting needed)
1. **The threads you already answered.** In r/ebooks `1x39d2e` and r/kindle `1tlu322` the askers are
   exactly the people. Post a short follow-up: "if you want me to just do it, send the PDF and I will
   send you the EPUB back." Offer it to the 2 or 3 people, not to the thread.
2. **r/InternetArchive** ("Best way to scan books to archive?", 26↑, 7c) and the digitizer crowd.
   They digitise books by hand. A tool that does OCR + chapters + EPUB is worth offering to them
   directly.
3. **Your own X account** (154 followers, they already watch you build side projects). One post:
   "free PDF to EPUB, no signup, nothing stored, and it fixes the paragraph mess" with a link.
4. **Where the founder has a network**: Discord servers, Slack communities, indie-author groups,
   university WhatsApp/Telegram groups with the person who keeps converting the course PDF by hand.

## What to say (the offer that converts a stranger)
> I built a free PDF to EPUB converter because the converters out there break your paragraphs.
> If you have a PDF you want as a real book, send it over and I will convert it and send you the
> EPUB back. Free, no account, I delete the file after.

Then, if they convert more than one book, that is the moment for the paid tier:
> The free one does one book at a time. I am opening 10 slots for $10/mo: 1,000 scanned pages a
> month, batch conversion of a whole shelf, and the file sent straight to your Kindle. Want in?

## The measurement that matters
Every manual conversion is a data point with the email attached. Keep them in one list with the
file type and page count, because that list is the evidence for the paid tier:
`grep -o '"email": "[^"]*"' conversions.log | sort -u` (plus your manual list).

Track it as: posts made, people who replied, files converted, people who asked for more than one,
people who said yes to $10. The first three are distribution, the last two are the product.

## Do not do these yet
- Do not buy Railway credits. $3.86 buys weeks at this traffic level, and the first customer is
  worth more than a month of hosting.
- Do not put a signup wall on the free path, and do not build Stripe. 5 yeses to the DM means build
  it, not 5 sales calls.
- Do not point public traffic at the Mac tunnel (the trycloudflare URL is random and dies when the
  Mac sleeps). Use the tunnel for DMs and manual use only. The public domain stays on Railway.
