Title: Your PDF to EPUB converter is not broken, your paragraphs are

Body:

I build a PDF to EPUB converter, so I get to read the complaints. The most common one is not "it
failed to convert" and it is not "the file was too big". It is that the book comes out reading like a
receipt, one paragraph for every printed line, and people give up somewhere in the first two pages.

Here is what is going on. A PDF is a fixed page layout. It stores the position of every glyph on a
sheet of paper and nothing about which words belong together. The paragraph structure is not in the
file. It is something a human inferred when they laid the page out, and it was never written down.

So the converter has to guess. The guess is usually that each line of text is a paragraph, because a
line is the thing a PDF hands over most directly. That is the receipt.

The second most common complaint is that the chapter menu is empty. A Kindle's jump-to-chapter list
is built from the EPUB's table of contents, the table of contents is built from the headings, and
the headings are the lines set in a larger font than the body text. If a converter never measures
font size it never finds them, and you end up with a 400 page book and no way to move around in it.

Running headers and page numbers are the third. The book title and the page number repeat on every
page of a print PDF. If the converter does not recognise them as furniture, they end up inside the
text, and your search breaks along with your navigation.

The fourth is hyphenation. When a word is split across two lines the hyphen has to go, otherwise
"informa- tion" is scattered through the chapter and your dictionary lookups stop working.

None of this is hard. It is four checks and they are not guesses once you know what the PDF is
holding.

Join at the block level, not the line level. Most PDFs store a paragraph as one block, so the block
boundary is the paragraph boundary and the line breaks inside it are just where the page ran out of
room.

Measure the body text size first, then treat anything clearly larger as a heading. In my converter
that is about 30% larger for a chapter title and 12% for a section heading.

Drop anything that repeats on more than half the pages near the top or bottom edge. That is a
running header, not content.

Drop text made only of digits and punctuation. That is a page number.

There is one check worth doing before you convert anything, and it decides your whole afternoon.
Open the PDF and drag across a paragraph. If the text highlights, the file has a text layer and a
converter can work with it properly. If you get a blank selection, the page is an image, and that
file needs OCR first. OCR output will contain typos that no amount of cleanup removes completely, so
know which one you have before you sit down with it.

The honest hard case is a two column academic paper with figures and tables. Equations and complex
tables need a different engine than a converter, and if that is what you have, read it on a tablet
instead of fighting the format. I do not think there is a web converter that should claim otherwise.

I looked at my own logs while writing this. Somebody converted 68 PDFs in 32 minutes, about 12,900
pages in total, and seven of those files were over my 500 page limit so they got rejected. I have no
idea who it was. If you have a stack of textbooks and you are hitting a cap, that is a real thing
you can hit and I would rather you knew before you started than after.

If you want to see what the output looks like before you commit to anything, I built a free one that
does the four checks above and nothing else: https://epub.ftak.net/?s=medium-paragraphs

No account, no watermark, and the file is deleted once you download it.
