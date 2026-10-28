# FIX-03 relative-date anchoring acceptance — 28 October 2026

Relative `today`/`tomorrow` dates now use an authored, timezone-aware source
timestamp. When a named source timezone is present, the parser converts the
timestamp to that zone before taking the calendar day. Missing or invalid
source timezones and naive/missing timestamps remain unresolved and request
review. Body and subject dates share this rule.

Gmail ingestion preserves both the authored `Date` header and provider receipt
time. A timezone-aware authored header can anchor relative dates; receipt-only
time cannot. Existing Gmail records without reference provenance fail closed
on replay. Attachment analysis inherits its parent's timestamp, source
timezone and reference trust. Historical operational imports now retain the
source timezone; reimport enriches older stored messages that omitted it,
queues reanalysis, and preserves existing correction fields.

Six focused regression tests cover a UTC/local-day boundary, a historical
import and replay, a Gmail authored/receipt date boundary, receipt-only and
legacy Gmail review behavior, and trusted/untrusted attachment inheritance.
The portable suite passed 212 tests with one private-data test deselected.
Changed Python files passed `ruff check`; `git diff --check` passed.

FIX-03 is accepted for supported fixture and import paths. Real corpus
accuracy has not been measured. Date-range parsing and unsupported temporal
cues were handled in the later FIX-02 fixture acceptance; actual
Windows/provider acceptance remains in ENV/REL.
