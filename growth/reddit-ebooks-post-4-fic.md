If you've ever turned a fic PDF into an EPUB and got words like "Džnger", "stu!" or "di!erent", the PDF isn't broken and you didn't do anything wrong.

Those are the "fi" and "ff" letter pairs. A lot of PDFs, especially ones exported from Kindle or Apple Books, draw "fi", "ff", "fl", "ffi" and "ffl" as one joined glyph. On the page it looks fine. But the hidden text layer underneath labels those glyphs as random characters, so every converter that reads the text copies the junk into your EPUB. In one 695-page fic I looked at, that was 1,200+ "fi"s and 600+ "ff"s.

I make a PDF to EPUB converter (disclosure: it's mine) and a reader sent me exactly this, so I fixed it this week. It works out which character stands for which letter pair from the words around it ("Džnger" can only be "finger"), and leaves real "!" alone. The same PDF also had each chapter's first paragraphs stored before the chapter title, so chapters started in the wrong place. That's fixed too.

It's free up to 150 pages, $5 for a longer book: https://epub.ftak.net/?s=post-ebooks-fic

If you have a fic PDF that still comes out wrong, send it my way and I'll look at it.
