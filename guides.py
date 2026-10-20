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
        "Scanned PDF to EPUB: OCR, and what to expect from it",
        "How OCR turns a scan of a book into searchable EPUB text, why the text will contain typos, "
        "and how to get a usable chapter structure out of a PDF that never had one.",
        """
<h2>What OCR does and does not fix</h2>
<p>OCR reads the pixels of a page and guesses the characters. It is good at clean printed text and
bad at anything unusual: a broken letter, a stain on the page, a decorative initial, a footnote in
small type. The output will contain typos, and no amount of downstream processing removes them
completely. What OCR does fix is the thing that makes a scan unusable: the text becomes selectable
and searchable.</p>
<h2>Structure is the second problem</h2>
<p>A book that was never digital has no chapter markers. The converter has to infer them. The usual
signals are a line in a larger font than the body, a short line on its own, or a line that starts
with a word like Chapter or Part. Where none of that is present you get flat text, and then the
table of contents is empty, no matter how good the OCR is.</p>
<h2>Practical order of work</h2>
<ol>
<li>Check the scan quality first. 300dpi, straight pages, no shadows.</li>
<li>OCR it, then read the first two pages of the result. The typos tell you how good the OCR was.</li>
<li>Look at the chapter list. If the structure is wrong, that is the file's fault, not the
reader's.</li>
</ol>
<h2>Try it</h2>
<p>Drop a scanned PDF below. Scans up to 200 pages go through OCR, free and with no account.</p>
""",
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
