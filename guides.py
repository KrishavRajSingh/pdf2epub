"""Guide pages for search traffic. Honest content, one tool link each.

ponytail: separate file so app.py stays about the app. slug -> (title, description, body html)
"""
GUIDES = {
    "pdf-to-epub": (
        "PDF to EPUB: how to convert a PDF into a real book",
        "Convert a PDF to EPUB with working chapters and a table of contents. What breaks in a PDF "
        "conversion, why one paragraph per printed line is the thing to check, and what to do about it.",
        """
<h2>What a PDF conversion actually has to get right</h2>
<p>A PDF is a fixed layout page. It stores the position of every glyph on a sheet of paper, not a
structure. An EPUB is a flow of paragraphs with a table of contents. Converting one to the other
means guessing where the paragraphs are, and that guess is where converters go wrong.</p>
<p>Four things decide whether the result is readable:</p>
<ul>
<li><b>Paragraphs.</b> The text of a wrapped paragraph has to end up as one paragraph. Plenty of
converters split it into one paragraph per printed line, which makes a normal book read like a
receipt. This is the single most common defect and the easiest to spot: open the EPUB and look at
the first paragraph.</li>
<li><b>Running headers and page numbers.</b> The book title and the page number repeat on every
page of a print PDF. If they are not removed they end up inside the text, and your search and
navigation suffer.</li>
<li><b>Hyphenated line breaks.</b> When a word is split across two lines, the hyphen has to go.
Otherwise your reader sees "informa- tion" everywhere.</li>
<li><b>Headings.</b> Headings are what turn a pile of pages into a book. If they are detected, you
get a clickable table of contents, and on a Kindle the jump-to-chapter menu works.</li>
</ul>
<h2>Does the PDF have a text layer?</h2>
<p>Open the PDF and drag across a paragraph. If the text highlights, the file has text and a
converter can work with it. If you get a blank selection, the page is an image, and you need OCR
first. Everything else depends on that one check.</p>
<h2>Fixed layout or reflowable?</h2>
<p>Reflowable text is what you want for a book: the text resizes to whatever screen it lands on.
Fixed layout keeps the original page as an image, which looks identical everywhere but cannot be
reflowed, cannot be searched, and on a small screen means zooming. For a scanned book, fixed layout
is the honest fallback.</p>
<h2>Try it</h2>
<p>The converter below strips headers and page numbers, joins wrapped lines into real paragraphs,
detects headings and builds a table of contents. No signup, and the file is deleted after the
download.</p>
""",
    ),
    "scanned-pdf-to-epub": (
        "Scanned PDF to EPUB: OCR a book scan, get real chapters",
        "Turn a scanned PDF into an EPUB with OCR, real paragraphs and a chapter list. The first 20 pages "
        "are free with no signup; a whole book is $5 once.",
        """
<p>Drop a scanned book into the converter. Each page goes through OCR, the lines get joined back
into paragraphs, and the headings become chapters in the table of contents. You get an EPUB3 file
that opens on a Kindle (through Send to Kindle), a Kobo, Apple Books and most phone readers.</p>
<p><a class="cta" href="/?s=seo-scan">Convert a scanned PDF</a></p>
<p><b>Free: the first 20 pages.</b> Try it on your own scan before you pay anything. No account,
and no watermark.</p>
<p><b>$5 once: the whole book</b>, up to 2,000 pages. You pay, come back to the upload box, and
the converter runs on the full book straight away. Full refund within 30 days if the result isn't
good enough.</p>
<h2>What OCR gets right, and what it doesn't</h2>
<p>OCR reads the pixels on a page and guesses the letters. On clean printed text it does well. It
struggles with broken letters, stains, decorative capitals and small footnote type, so the EPUB
will have some typos. Check the first two pages of the free preview: if those read fine, the rest
of the book will too.</p>
<p>A scan has no chapter markers, so the converter infers them from bigger type, short lines
standing alone, and lines that start with "Chapter" or "Part". If a book has none of those, you
get one long text and an empty table of contents. The free 20 pages show you which case you're
in.</p>
<h2>Scans that other converters skip</h2>
<p>Many PDFs from libraries and archives are scans with a little real text on top: a "Downloaded
from" footer, a library stamp, a filled-in form field. Converters that check "does this PDF have
text?" see that line, skip OCR, and hand back an almost empty book. pdf2epub looks at how much of
each page is actually text, so those scans still get read.</p>
<p>Internet Archive PDFs come with their own text layer, which is often messy. pdf2epub rebuilds
the paragraphs from it instead of keeping one line per printed line.</p>
<h2>Getting a better result</h2>
<ul>
<li>Scan at 300 dpi, pages straight, no shadow along the spine.</li>
<li>One page per image works better than two-page spreads.</li>
<li>No scanner? <a href="/scan">Scan a book with your phone</a>: take photos of the pages and
they become the book.</li>
</ul>
<h2>Your file</h2>
<p>The PDF is never saved. The finished EPUB is deleted after you download it, or after an hour
if you don't.</p>
<p>Next: <a href="/guides/send-pdf-to-kindle">get the EPUB onto a Kindle, Kobo or Boox</a>.</p>
""",
        [
            ("Can I convert a scanned PDF to EPUB for free?",
             "Yes, the first 20 pages of a scan. A PDF that already has text is free up to 150 pages."),
            ("How much does a whole scanned book cost?",
             "$5 once for one book up to 2,000 pages, OCR included. There's no subscription. If you're not happy "
             "with it, you get a full refund within 30 days."),
            ("Will the EPUB have typos?",
             "Some, yes. All OCR makes mistakes on worn or unusual print. Clean, straight 300 dpi scans give the fewest."),
            ("Does it work on Kindle?",
             "Yes. Send the EPUB with Amazon's Send to Kindle and it shows up in your library. Kobo and Apple Books "
             "open it directly."),
            ("My scan came out empty in another converter. Will this one work?",
             "Probably. That usually happens when a scan has a stamp or footer with real text, so the other converter "
             "skips OCR. pdf2epub runs OCR on those pages anyway. Try the free 20 pages to check."),
            ("Can I convert a book I bought on Kindle or Kobo?",
             "No. Store books are locked with DRM and aren't PDFs."),
        ],
        "Scanned PDF to EPUB",
    ),
    "send-pdf-to-kindle": (
        "How to get a PDF book onto a Kindle, Kobo, Boox or your phone",
        "Send a converted EPUB to your Kindle by email, load it on Apple Books, Kobo or Boox, and "
        "what side-loading means on newer Kindles.",
        """
<h2>Kindle, the easy way</h2>
<p>Amazon's Send to Kindle address is an email address. Attach the EPUB and put "convert" in the
subject line. The file lands on every device on your account, and Amazon converts the format for
older devices that do not accept EPUB directly. That is the whole workflow, and it works from a
phone.</p>
<h2>Kobo, Boox, PocketBook</h2>
<p>These read EPUB natively. Kobo also has its own KEPUB variant, which is an EPUB with a little
extra, and some Kobo apps are pickier about it. USB is the reliable path: connect the reader as a
mass storage device and copy the file into the books folder. On a Boox or a PocketBook you can also
install KOReader, which reads EPUB, PDF, DOCX and CBZ in one app and renders PDFs with reflow.</p>
<h2>Apple Books and phones</h2>
<p>Apple Books takes EPUB and PDF. On iOS the file comes in through Files or a share sheet, and it
is usually easier to convert first and open the EPUB than to read a PDF in a viewer that cannot
reflow.</p>
<h2>Side-loading on 2026 Kindles</h2>
<p>MTP file transfer has been getting restricted on newer firmware. Copying over USB still works, and
Send to Kindle by email is unaffected, which is why the email route is the one that has not broken
for anyone.</p>
""",
    ),
    "pdf-to-epub-vs-calibre": (
        "PDF to EPUB: this converter vs Calibre",
        "An honest comparison of a web converter and Calibre for turning PDFs into EPUBs: setup, "
        "quality on text PDFs, scans, large files and privacy.",
        """
<h2>Calibre is excellent, and it is a lot of software</h2>
<p>Calibre is free, local, and it can do things no web converter does: edit the EPUB afterwards in
Sigil, manage a large library, convert on a schedule, output KEPUB. If you already have it and you
like owning your tools, keep using it.</p>
<h2>Where it gets painful</h2>
<p>Installing it, learning the conversion settings, and accepting the output quality. Calibre's PDF
input is the weakest part: it does not have a document structure model the way Word or InDesign
does, so it has to guess. Two settings do most of the work: <code>--enable-heuristics</code> (which
removes headers and footers, unwraps lines and removes hyphens) and <code>--output-profile
kindle</code> for device-sized output. Even then, the paragraphs sometimes come out wrong and you
end up fixing the file by hand in Sigil.</p>
<h2>What a web converter is good at</h2>
<p>One file, no install, no library to maintain, and nothing left on your machine. It is the right
tool when you have one PDF of a textbook and you want it on the Kindle tonight. It is the wrong tool
when you have four hundred of them and you want a pipeline.</p>
<h2>Scans specifically</h2>
<p>Calibre needs an OCR plugin wired up and configured before it will read a scan, and the result
still needs cleanup. OCR built into a converter is one click. If your book is a scan, that is the
difference between an evening and a weekend.</p>
""",
    ),
}

INDEX_BODY = """
<p>Short, practical guides. No newsletter, no signup.</p>
<ul>
<li><a href="/guides/pdf-to-epub">PDF to EPUB: how to convert a PDF into a real book</a></li>
<li><a href="/guides/scanned-pdf-to-epub">Scanned PDF to EPUB: OCR and what to expect</a></li>
<li><a href="/guides/send-pdf-to-kindle">Getting a PDF book onto a Kindle, Kobo, Boox or phone</a></li>
<li><a href="/guides/pdf-to-epub-vs-calibre">This converter vs Calibre</a></li>
</ul>
"""
