# PIPE-03 document layout and decoding acceptance — 28 October 2026

Attachment extraction now records exact offsets into its combined text. HTML
table rows retain cell separators; DOCX paragraphs and table rows remain in
document order; PDF pages have page spans; XLSX cells and rows have sheet,
row and cell locators. An attachment occurrence stores its own locators and
charset, and its validated date assertions use the smallest containing
locator. Blob reuse cannot replace that occurrence's source location.

Gmail text parts and text/HTML attachments honor declared MIME charsets.
Unsupported or damaged decoding is recorded without source text in logs.
Attachments with poor text are marked `needs_text_review` and are not analyzed;
empty extraction is `needs_ocr_or_review`. Poorly decoded mail gets an
explicit review prompt and cannot create entities or downstream grades from
that text. The quality indicator records replacement/control characters and
their ratio. This is a conservative signal, not a language-quality score.

Representative synthetic fixtures cover HTML, generated DOCX/XLSX files,
PDF page offset assembly, declared Latin-1 decoding, damaged bytes, resource
abstention and source-linked spreadsheet evidence. PDF page text extraction
itself is supplied by `pypdf` and page-offset assembly was tested with a page
stub; scanned-image OCR is not included. The portable suite passed 263 tests,
one private-data test was deselected, and lint passed. No measured accuracy
gain or corpus-wide layout claim is made.
