# Free growth tools and the weekly workflow

Checked 2026-10-26. Every tool here is free at the level we need. Anything that needs an account
is yours to sign up for (Claude cannot create accounts).

## The tools

| Tool | What it does for us | Setup (you) | Cost |
|---|---|---|---|
| **F5Bot** (f5bot.com) | Emails you when a keyword shows up on Reddit, Hacker News or Lobsters. This is how we find people asking "how do I convert this PDF" while they are still asking. | Sign up with your email, add the keywords below | Free tier: alerts are delayed, very common words are refused, each keyword has a daily hit cap |
| **Talkwalker Alerts** (talkwalker.com/alerts) | Same idea for news, blogs and forums; covers more than Google Alerts | Sign up, add `"epub.ftak.net"` and `"pdf2epub"` | Free |
| **Google Alerts** | Backup for mentions of the domain | google.com/alerts, add `"epub.ftak.net"` | Free; known to miss things |
| **Google Search Console** | Which searches show the site, and where it ranks | Already set up (sitemap read Oct 23) | Free |
| **Bing Webmaster Tools** (bing.com/webmasters) | Bing index; Bing feeds Copilot and DuckDuckGo, and possibly ChatGPT search (OpenAI does not confirm this). Since Feb 2026 it has an "AI Performance" report for Copilot citations. | Import the site from Search Console (no re-verification), submit `https://epub.ftak.net/sitemap.xml` | Free |
| **IndexNow** | Tells Bing, Yandex and others the moment a page changes. Google does not take part. | Code change in `app.py` (a key file route + one ping after deploy). Claude can add it. | Free |
| **Ahrefs Free** (formerly Ahrefs Webmaster Tools) | Who links to us (up to 1,000 backlinks), which pages get search traffic, and a site audit of 170+ SEO issues | Sign up, verify through Search Console | Free for a verified site |
| **Gmail drafts via `gws`** | Our outreach pipeline: Claude writes the drafts, you press send | Already working | Free |
| **`/funnel`** | People per step, by source tag | Deploy + `FUNNEL_KEY` (see earlier) | Ours |

Skipped: Syften, RedShip, Subreddit Signals and similar Reddit monitors (paid, $19-49/month).
GummySearch shut down. OctoLens has a free tier but is aimed at teams; F5Bot covers our case.

## F5Bot keywords

Keep them specific, or the daily cap is eaten by noise:

- `pdf to epub`
- `convert pdf to epub`
- `pdf to kindle`
- `scanned pdf epub`
- `pdf on kindle`
- `pdf kobo`
- `calibre pdf`
- `epub.ftak.net` (anyone linking us)

## Free listings worth one PR or post

- **inchei/awesome-kindle** on GitHub (85 stars, last updated 2026-10-21). Its "Generator" section
  already lists hosted tools marked "(Website, not open source)", including paid ones. A one-line
  pull request:

  `* [pdf2epub](https://epub.ftak.net/?s=awesome-kindle) (Website, not open source) - Converts a PDF into an EPUB for Kindle with real paragraphs, chapters and a table of contents; running heads and page numbers removed, scans read with OCR. Free for text PDFs up to 500 pages, no account.`

  Opening the PR posts publicly under your GitHub account, so it needs your go-ahead.
- **KindleTweaks/Awesome-Kindle** (393 stars) is about jailbreak tweaks, not converters. Skip.
- The other "awesome ebook" lists are book lists, not dormant tool lists. Skip.

## The weekly loop

**Every day, 10 minutes**
1. Read the F5Bot email.
2. Answer 1-3 threads where someone has the problem right now. Help first: say what is wrong with
   their PDF and how to fix it with any tool. Mention pdf2epub once, say you built it, and use a
   tag link like `https://epub.ftak.net/?s=r-kindle`.

**Every Monday, 30 minutes**
1. Open `/funnel?k=...&days=7`. Find the smallest red percentage. That step is the week's fix.
2. Search Console and Bing: which searches showed the site, and which pages. One new guide page
   per week aimed at a search you almost rank for.
3. Send 5 pitches from `growth/newsletter-pitches.md` (Claude drafts, you send). Log them in
   `growth/outreach.md`.
4. Follow up once, a week later, on pitches with no reply. Then stop.

**Every month**
1. Ahrefs Free: new backlinks, site audit errors.
2. Re-read `/funnel?days=30` by source. Drop channels that send visits with 0 conversions; double
   the ones that convert.
