# Sentence and clause boundary increment — 28 October 2026

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

FIX-01 remains open: the separator set and scope policy need regression
verification on actual examples, and other constructions such as coordination,
quoted history and uncommon abbreviations still require review. The modified
module compiled; no reviewed action recall or end-to-end gain is claimed.
