Title: What a scanned textbook actually costs to convert

Body:

Someone asked me for a converter that actually works, so I did the thing I would have done anyway.
I took one 300 page scanned textbook and worked out what every option really charges for it, once
you add the rest up.

The free ones are good, and two of them are free in a way that matters. freepub.app runs entirely in
your browser, so nothing is uploaded and there is no file size limit. Its default output is a fixed
layout EPUB, which means each page is an image. It looks identical everywhere, but you cannot
reflow it, you cannot search it, and on a small screen it means zooming. It has text modes now,
where the text is extracted with OCR as a fallback.

pureepub.com reflows text and gives you a KePub for Kobo. Files are processed in memory and wiped
after the download. It says plainly that scanned image books need OCR first, which is more honest
than most.

Calibre is free and runs on your machine. Two flags do most of the work, --enable-heuristics to
strip headers and footers and remove hyphens, and --output-profile kindle. It still needs an OCR
plugin before it will touch a scan, and the output often still needs fixing by hand in Sigil.

The one that costs money is convert2epub.com. Ordinary text PDFs are free and need no account.
Scans are charged per page: 1 credit per OCR page, 1 credit per 10 pages to recover a text layer
that already exists, and 2 credits per page for the Pro pass, which uses Mathpix and rebuilds
formulas and tables. Credits do not expire. 1,000 credits is $11, so a 300 page scan lands around
$3.30, or $6.60 with the Pro pass. New accounts get 30 free credits. Files are deleted
automatically, but signed in files are kept for 30 days.

So a scanned textbook is free if you are willing to accept page images, and roughly three to seven
dollars if you want searchable reflowed text out of a scan.

That is also the awkward part of the free lane. freepub.app and pureepub.com already promise free,
local, no account, nothing stored. My pitch would be identical to theirs and that is exactly the
problem.

What I actually wanted to know when I started was what breaks in a conversion, since that is the
complaint in every thread I have read on this. One paragraph per printed line, so a normal book
reads like a receipt. Running headers and page numbers ending up inside the text. And a table of
contents that comes out empty, which is the one nobody mentions until they open the file on a
Kindle and find the chapter menu does nothing.

I built a free converter around fixing those: https://epub.ftak.net/?s=medium-cost

Text PDFs are free, and scans up to 200 pages go through OCR with no account and no credits. I am
not going to pretend it beats Mathpix on equations, that is the one case where paying convert2epub a
few dollars is the right call.

Happy to run the same comparison on other files, or on a 500 page textbook, if that is more
interesting than a general one. Comment with the file you want tested and I will run it.
