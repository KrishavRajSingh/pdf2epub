# Why Jack's uploads failed, and the architecture that fixes it (2026-11-05)

## What happened

On 11-05, between 00:10 and 00:45 UTC, the first Shelf buyer sent ~20 books. Three got a 502:

| Time (UTC) | What the logs show | Cause |
|---|---|---|
| 00:10 submit → 00:11:57 502 | `Child process [2899] died`, no traceback | Worker killed for memory |
| 00:37 submit → 00:38 502 | `Child process [2902] died`, no traceback | Worker killed for memory |
| 00:39 submit → 00:44 502 | Server logged `ok pages=302 ocr+fig` at 00:49 | Request ran past Railway's 5-minute limit |

The Railway "Deployment crashed" emails are a separate thing. They arrive when a deploy replaces the old container.

## Root causes (measured, not guessed)

### 1. Every figure becomes a full-size lossless PNG, and all of them sit in memory at once

`_blocks()` renders each figure region at `FIG_SCALE = 3` (216 dpi) and saves it as PNG. PNG is the wrong format for photos. `convert()` then calls `list(_blocks(doc))`, so every figure in the book is held at once, and `build_epub()` copies them into a `BytesIO` zip and again into `getvalue()`.

Local profile (same code as production, a Shelf key, macOS peak RSS):

| Input | Output EPUB | Time | Peak memory |
|---|---|---|---|
| 800-page text book, 7 MB | <1 MB | 19 s | 120 MB |
| 120 pages with a photo on each, 113 MB | **486 MB** | 165 s | **645 MB** |
| 300 pages with a photo on each, 284 MB | **1,216 MB** | **412 s** | **1,304 MB** |
| The 120-page photo book again, same worker, after other conversions | 486 MB | 176 s | 774 MB (creeps up) |

The EPUB comes out about **4× bigger than the PDF**. Railway's trial plan gives the whole service **1 GB of RAM**, and we run **2 uvicorn workers** in it. One photo-heavy book uses about 650 MB, so two at once, or one bigger one, gets the worker killed. Python also does not give freed memory back to the OS, so each worker stays big after a heavy book (the "creeps up" row).

The same 30 figures: PNG 127 MB, JPEG at quality 80 is 18 MB (**7× smaller**). My test images are noisy, the worst case for JPEG; real photos compress better.

### 2. Conversion runs inside the HTTP request

Railway's docs (networking/public-networking/specs-and-limits) say: "HTTP requests can run for up to 15 minutes if data keeps transferring ... and are otherwise closed after 5 minutes with no data transferred." Our `/convert` sends nothing until the EPUB is ready. OCR runs one page at a time, about 2 s per page in production (302 pages took ~10 min). Anything over ~5 minutes is cut off, and the finished EPUB is thrown away.

### 3. Heavy work shares the web process

A conversion that runs out of memory kills the uvicorn worker. That worker is also serving other visitors, and the buyer gets a blank 502 instead of a message.

### 4. The trial plan is the bigger risk

The trial plan caps RAM at 1 GB, and its credits run out (the 11-03 email said 50% was used). When they run out, the whole service stops, including the paid tier.

## The architecture that fixes it

### Stage 1: lighter conversions (a few hours, no new infra)

1. **Figures as JPEG** (quality 80) unless PNG is smaller (line-art maps). Cap the long side at 1,600 px. Expect EPUB size and memory down about 5-7× on photo books.
2. **Do not hold the whole book.** Write figures and chapters into a temp EPUB on local disk (`/tmp`, not the volume) as they are made, return it with `FileResponse`, and delete it after sending. Open the upload from the spooled temp file instead of `await f.read()` into bytes.
3. **Run each heavy conversion in a child process**, one at a time (`ProcessPoolExecutor(max_workers=1, max_tasks_per_child=1)`). If it runs out of memory, only that job dies, and the server returns a clear "too heavy, email it to me" message. Memory goes back to the OS after every book, so no creep. Light text books can stay inline.
4. **Pre-check weight:** count image pages and image bytes before starting. Very heavy books go straight to the job path in stage 2.

### Stage 2: background jobs (about a day)

- `POST /convert` saves the upload to `/tmp/jobs/<id>.pdf` and returns `{job: id}` right away.
- One worker process converts jobs in order and writes `/data/jobs/<id>.json` (`queued`, `running page 120/302`, `done`, `failed`).
- The page polls `GET /job/<id>` every 3 s and shows progress. When the job is done, it downloads `/job/<id>/epub`.
- The PDF is deleted when the job ends. The EPUB is deleted after download, or after 1 hour.
- If the buyer left an email, mail the download link when the job is done, so closing the tab is fine.
- No Redis needed: job state is files on the volume, so both web workers see it.

This removes the 5-minute limit completely, because every request is short. It also lets OCR use both vCPUs (2 tesseract processes), which roughly halves scan time.

Copy change needed: the site says files are "processed in memory and deleted after the download". With jobs, it should say they are deleted within an hour.

### Stage 3: hosting plan (needs the user's yes, it is spend)

Move pdf2epub from Trial to Railway Hobby ($5/month minimum, usage-based, up to 48 GB per service). Set the memory limit at 2 GB. With stage 1, 1 GB is probably enough day to day, but Hobby removes the "credits run out, site stops" risk. Revenue so far is $15 ($5 One Book + $10 Shelf).

### Rejected

- **Vercel/serverless:** the 4.5 MB request body limit, and no calibre or tesseract.
- **Cloudflare Workers:** no native binaries.
- **Modal or Fly machines per job:** works, but it means another vendor and another bill for one subscriber. Stage 2 on the same Railway service does the job.
- **Streaming keep-alive bytes during conversion** to stretch the limit to 15 min: hacky, still breaks past 15 min, and still holds everything in memory.

## Order

Stage 1, items 1 and 3, first: they fix both memory kills. Then stage 2, which fixes the timeout and adds progress. Stage 3 whenever the user says yes.
