# FIX-01 sentence and clause boundary acceptance — 28 October 2026

The source-aligned sentence splitter protects periods and query punctuation
inside URLs, decimal points and common abbreviations. Trailing URL punctuation
can still end a sentence or clause. `etc.` at a sentence end no longer merges
the next obligation into a completed preceding sentence.

Action clauses split at semicolons, `but`, and a coordinated new explicit
`must`/`should`/`please` obligation. Negation and completion stay local, so
`already registered and must upload` retains the upload action. Quoted `>`
reply lines are masked with equal-length spaces before extraction, preserving
authored evidence offsets. The engine also excludes standard reply-header
history. A quote-only message creates no assignment, date or action.

Eight focused fixture tests cover URL/decimal punctuation, a semicolon inside
a URL, completed and negated clauses, abbreviations, authored offsets after
quoted lines, quote-only mail and reply headers. The portable suite passed
248 tests with one private-data test deselected. Changed Python files passed
`ruff check`; `git diff --check` passed.

FIX-01 is accepted for these supported boundaries. The rule action detector
is still not a learned extractor. The versioned shared authored/quoted
preprocessing contract was completed later under PIPE-02. No reviewed recall
or accuracy gain is claimed.
