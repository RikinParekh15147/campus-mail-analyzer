# Sentence and clause boundary increment — 28 October 2026

FIX-01 is now accepted for supported fixture boundaries after URL punctuation,
coordinated obligations, quoted-history masking and replay tests. See
[FIX-01 acceptance](FIX01_ACCEPTANCE.md). The notes below describe the
earlier partial implementation.

The local splitter now returns source-aligned spans while preserving URL paths,
query strings, decimals and common abbreviations. It splits at sentence-ending
punctuation and newlines only when that punctuation is not inside a URL or a
known abbreviation. Call sites in date-role detection and the engine continue
to receive `.start()`, `.end()` and `.group()` evidence spans.

Action detection now splits contrasting clauses at semicolons and `but`, while
preserving source offsets and ignoring separators inside URLs. Negation and
completion checks apply to each clause. A completed registration clause can no
longer suppress a separate “must upload” clause in the same sentence. This is a
rule-bound improvement, not a learned action detector.

At this stage FIX-01 was still open. Later fixture acceptance covers explicit
coordination and quoted history; uncommon wording remains a candidate for
reviewed evaluation. No measured action recall or end-to-end gain is claimed.
