# PIPE-04 attachment occurrence acceptance — 28 October 2026

Identical attachment bytes share one owner-scoped blob/resource. Each parent
message gets a distinct analysis message carrying its source timestamp,
timezone, thread and trust state. An optional provider attachment ID keeps two
separate items under the same parent distinct; the occurrence stores its own
filename. The resource retains all analysis message IDs while the singular
`analysis_message_id` remains a compatibility pointer to the latest item.
Reattaching the same item is idempotent. Invalid parent references are checked
before writing the blob or resource.

Synthetic replay tests cover two parents with different relative dates, two
provider items under one parent, duplicate reattachment, and invalid parent
references. The portable suite passed: 253 tests, one private-data test
deselected. Existing pre-provider-ID occurrence keys require PIPE-05 migration
planning; this fixture acceptance does not assert measured accuracy.
