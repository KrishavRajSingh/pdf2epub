# Tier-1 reply pack — Reddit threads where pdf2epub questions are unanswered

Built 2026-10-20 from `growth/question-sheet.csv` (319 rows). Live state verified today. Every reply: **answer first, tool second, link last**. Never paste a draft as-is in a sub that bans generated text (see r/Calibre).

Link format: `https://epub.ftak.net/?s=<tag>` — the `s` value is the ref key you will see in `/stats` (`ok_by_ref`).

## Rules map (verified today + your existing intel)

| Sub | Link in comment? | Self-promo | Agent-written text allowed? | Source |
|---|---|---|---|---|
| r/ebooks | yes (plain link, flair "Self Promotion" for posts) | allowed with flair | no rule against it found; still rewrite in your own voice | no published rules; precedent: tool post 96↑/45c (`1t3kroz`) |
| r/kindle | **no** — no website names, no self-promo | no | no AI rule found | your intel; enforcement active (comments removed in `1tlu322`) |
| r/Calibre | no | tool posts need an **AI CONTENT DISCLOSURE** header | **NO — generative-tool-written comments are banned** | sub rules post `1wx55zn`, 308↑, 2026-10-04 |
| r/ereader | **no** — "no advertising of any kind" | posts only (precedent: tool post 314↑ `1spubjk`) | no AI rule found | your intel + live precedent |
| r/Annas_Archive | — | — | — | REMOVED, do not repost |

r/Calibre rule text (verbatim, `1wx55zn`): *"The use of generative tools to write or refine a post or comment is banned. Posts and comments must be written by a human being not a generative tool."* → for the three r/Calibre targets below: **write it yourself from the facts column. Do not paste this text.**

## Targets (fresh → intent order)

### 1. r/ebooks — "PDF to EPUB converters, experiences & quality?" (9 days, 17↑, 51 comments)
https://reddit.com/r/ebooks/comments/1x39d2e/pdf_to_epub_converters_experiences_quality/
- **Already answered:** convert2epub.com, cloudconvert, FreeReader, "flipbook software". Consensus: "PDFs cover a multitude of sins."
- **Your angle:** nobody here mentions chapters/TOC or OCR-for-scans. Both are your differentiator and the thread's exact complaint ("PDF is so clumsy").
- **Facts to give:** what breaks in a PDF→EPUB conversion (headers/footers, hyphenation, columns, page numbers) and how a converter should handle it (strip repeated headers, join hyphenated words, detect headings → TOC, drop page numbers). Text PDFs convert well; image-only PDFs need OCR and get worse results.
- **Reply draft:** "The thing that decides it is whether the PDF has a text layer. Native-text PDFs convert cleanly if the converter strips running headers/footers, drops page numbers, joins hyphenated line breaks and detects the heading levels to build a TOC — that's what makes the difference between 'a pile of page images' and a book you can actually navigate. Image-only PDFs (scans) are a different job: they need OCR, and even then reflow is approximate. Happy to share the checklist I use to tell the two apart before you convert anything."
- **Link:** `https://epub.ftak.net/?s=ebooks-1x39d2e` — optional, as a second line: "one free converter that does the header/TOC part if you want to compare: <link> (no signup, files aren't stored)."
- **Then:** reply again under the OP's own reply ("I guess I will just have to try") with the link + "yes, text PDFs are the good case; if yours is a scan, OCR is the difference."
- **Rules:** link OK. Don't editorialize; answer as a user, not the maker.

### 2. r/Calibre — "Is there a plugin for converting research paper PDFs into ebooks?" (6 days, 4↑, 14 comments) ⚠️ human-only
https://reddit.com/r/Calibre/comments/1x5a2d4/is_there_a_plugin_for_converting_research_paper_pdfs_into_ebooks/
- **Already answered:** "use marker", "Claude Code", Calibre is bad at it; one comment says "AI will make shit up in this situation".
- **Facts to write in your own words:** Calibre's PDF→EPUB produces page images because a two-column academic PDF has no reliable reading order. Any tool will struggle with figures, tables and footnotes. What *is* fixable: dropping running headers, keeping figure captions attached to the figure, and getting a TOC from the section headings. For a 6" screen, a used iPad is often the honest answer.
- **Ask yourself before replying:** if your only reply is "try my tool", the mods may read it as astroturf (their rules allow tool discussion only when it is "a genuine response to a post or comment and is not simply astroturf marketing").
- **If you post a tool there later:** the post MUST begin with a header titled **AI CONTENT DISCLOSURE** stating honestly how much generative tooling was used (code, docs, tests).

### 3. r/Calibre — "How do I convert pdfs to EPUB?" (94 days, 17↑, 35 comments) ⚠️ human-only
https://reddit.com/r/Calibre/comments/1uzcek2/how_do_i_convert_pdfs_to_epub/
- **OP's real problem:** PDF **manga** conversion stalls at 1% "converting to html".
- **Facts:** manga PDFs are page images — HTML conversion stalls because there is nothing to convert; the standard route is export pages as images (Foxit "Export to images" → select all → zip → Calibre "Add books" as images). A page-image EPUB is fine on a Kindle; a reflowed text EPUB is impossible for manga.

### 4. r/ebooks — "What is your biggest frustration with current eBook apps (Kindle, Libby…)" (302 days, 14↑, 67 comments)
https://reddit.com/r/ebooks/comments/1psh9u5/what_is_your_biggest_frustration_with_current_ebook_apps_kindle_lib/
- **Your angle:** the fragmentation answer — a file you find in one place, open in another app, highlights that don't sync, and PDFs that behave like a photocopy.
- **Reply draft:** "Biggest one for me is the gap between 'I own the file' and 'I can read it'. A PDF is fine on a laptop and terrible on a 6" screen, so it ends up unread; converting it gives you a book, but now the file exists in three places (laptop, Kindle, phone) and the highlights don't follow. If I could pick one fix it'd be: one file that works on every screen, with notes that sync."
- **Link:** `https://epub.ftak.net/?s=ebooks-1psh9u5` — only if someone asks for a tool in the thread; otherwise answer without it.

### 5. r/kindle — "Any advanced tool to decently convert PDF academic papers to EPUB?" (149 days, 5↑, 37 comments) — advice only, no link
https://reddit.com/r/kindle/comments/1tlu322/any_advanced_tool_to_decently_convert_pdf_academic_papers_to_epub/
- **Already answered:** Kindle Scribe, Calibre (PDF→HTML→EPUB), "textbooks → used iPad", ChatGPT/paper2epub don't work.
- **Facts to add:** academic two-column PDFs have no reliable reading order, so expect column bleed; figures/tables are the real blocker, not the text. If the paper has a DOI, the published EPUB or a page-by-page screenshot is often faster. Nothing converts a figure-heavy paper into a good 6" EPUB — the honest answer is Scribe or a tablet.
- **No link, no tool name** (r/kindle: no website names, no self-promo).

### 6. r/kindle — "Is there any good PDF to EPUB / MOBI converter?" (201 days, 2↑, 32 comments) — advice only
https://reddit.com/r/kindle/comments/1sa7guk/is_there_any_good_pdf_to_epub_mobi_converter/
- **Already answered:** freepub.app (community-made, strong endorsement), Send-to-Kindle with subject "Convert", "if it's a scan you need solid OCR", "text → skip conversion and read the PDF".
- **Facts to add (no product):** the four checks before you convert — does the PDF have a text layer (open it and select text; if it highlights, it's text), are there two columns, is it a scan (then OCR, and expect typos), does it have running headers (they end up inside paragraphs). MOBI is legacy — Kindle converts EPUB via "Send to Kindle" with subject "Convert" or the app's import; no local MOBI writer is worth installing.
- **Also answer the dangling sub-question** ("implementing saving the file to .mobi?"): MOBI is deprecated, EPUB3 is what to target.

### 7. r/ebooks — "Anyone else keep their own EPUB/PDF library instead of buying into a subscription?" (64 days, 55↑, 29 comments)
https://reddit.com/r/ebooks/comments/1vqoth7/anyone_else_keep_their_own_epub_pdf_library_instead_of_buying_into_a_s/
- **Your angle:** the owning side — the file you bought should work on your device, offline, forever, no lease. PDFs are the weak link (they don't reflow, they can't be read comfortably on e-ink), so the "keep your own library" crowd is exactly the PDF→EPUB crowd.
- **Reply draft:** "Same here — own files, no subscription. The annoying part is the PDFs in my own library: they were 'ebooks' I bought years ago and now they open like a photocopy on an e-ink screen. Everything else is fine until you hit a PDF."

### 8. r/Calibre — "Can you please help me in converting a pdf to epub?" (64 days, 1↑, 27 comments) ⚠️ human-only
https://reddit.com/r/Calibre/comments/1vqi568/can_you_please_help_me_in_converting_a_pdf_to_epub/
- **Facts:** Calibre's own workflow is what this sub expects: `ebook-convert file.pdf file.epub`; for two-column PDFs try `ebook-convert in.pdf out.epub --pdf-engine calibre`; if it stalls, it's a scan or a complex layout — convert to HTML first and inspect, or use a tool that does OCR for the image-only case.

### 9. r/kindle — "Side loading via MTP now disabled for 2026 Kindles?" (18 days, 0↑, 44 comments) — advice only
https://reddit.com/r/kindle/comments/1wvccvg/side_loading_via_mtp_now_disabled_for_2026_kindles/
- **Facts:** for 2026 Kindles, MTP (MTP-only file transfer) is being replaced by USB mass-storage / MTP-off mode; send-to-kindle by email still works with the "Convert" subject for EPUB. If side-loading from a computer feels broken, the least-friction path is email-to-Kindle, then the file appears on all devices.
- **Note:** this is the delivery question the sheet flags 48 times — the answer (send-to-kindle) is also the answer to "I don't want an app".

### 10. r/ereader — "What do you do with physical books that you wish were on your e-reader?" (106 days, 5↑, 67 comments) — advice only
https://reddit.com/r/ereader/comments/1uoxaky/what_do_you_do_with_physical_books_that_you_wish_were_on_your_e/
- **Facts:** the honest options: (a) scan + OCR — slow, and OCR text has errors; (b) look for a library loan of the digital edition; (c) check the publisher's "read on your phone" / audiobook option; (d) accept that some books stay paper. If you scan, keep the scan set consistent (same resolution, same file naming) so later EPUB builds stay in order.
- **This is your accessibility + own-books crowd** — the group most likely to pay later. Answer well here without a link; identify yourself as a maker later in DM, not in the thread (r/ereader: no advertising).

### 11. r/Calibre — "Converting PDF to EPUB" (677 days, 24↑, 43 comments) ⚠️ human-only
https://reddit.com/r/Calibre/comments/1hc2utk/converting_pdf_to_epub/
- **Facts:** long-standing thread; the recurring answer is "PDFs are fixed-layout, so conversion is guesswork; use calibre's `--pdf-engine calibre` and accept the damage, or keep reading PDFs on a tablet". If the thread is still active, a short factual answer about text-layer detection and OCR is more useful than a tool.

## Posting order and rules of engagement
1. Freshest first: 1x39d2e (r/ebooks) → 1x5a2d4 (r/Calibre, human-only) → 1uzcek2 (r/Calibre, human-only) → 1wvccvg (r/kindle).
2. Max 1 comment per sub per 48 h. Never two links in one comment. Never reply to the same comment twice in a day.
3. Comment length: answer in 3–6 sentences; the link on its own line; no emoji, no "check out my".
4. Stay in the thread 60–90 min after posting and reply to any follow-up.
5. If a mod removes a comment, do not re-post, do not reply to the mod, move on.
6. Never mention archive/piracy sites; r/kindle: never name our site.
7. Measure: `/stats` → `ok_by_ref` after 72 h. Tag = thread id. 0 conversions on a tag → don't reply in that sub again.

## Before you post anything
- [ ] Rewrite every draft in your own words (r/Calibre: mandatory, other subs: strongly recommended — AI-sounding replies get ignored and may be treated as astroturf).
- [ ] Check the thread's top comments again for a newer answer (someone may have solved it while this pack was written).
- [ ] Add flair "Self Promotion" only if you post a link-post, not a comment.
