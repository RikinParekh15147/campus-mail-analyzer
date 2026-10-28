# DATA-05 / DATA-09 reservation and source policy — 28 October 2026

The accepted private run is `artifacts/research/data05-20261028-reserved-v2`.
It is pinned to the DATA-03 run, DATA-04 report and membership SHA-256
`26ef07b07020553080a83b7d9f8ed44f5160a421e6346cb552259ccf663f8e21`.
No message text, member ID or reviewer identity from the private run is committed.

## Allocation and pack

| Measure | Result |
|---|---:|
| Records / provisional guards accounted for | 17,291 / 7,859 |
| Development guards / records | 6,273 / 13,623 |
| Sealed guards / records | 1,586 / 3,668 |
| Scoped development review guards | 84 |
| Scoped development pack rows | 189 (151 available text, 38 context-only) |
| Sealed scoped review queue | 30 independent guards, ID-only |
| Parent / context / grouping references in pack | 76 / 382 / 83 |

The allocation uses a fixed SHA-256 policy and places each complete
`provisional_split_guard_id` in exactly one partition. It includes all sources
for leakage accounting. The development pack uses small scoped academic guards,
keeps their complete scoped membership, preserves pseudonymous thread, parent,
context, grouping and update-family links, and hides weak labels from reviewers.
The 189-row pack contains no source document IDs or raw provider identity map.
The private identity map is a separate ignored sidecar for later adjudication.
Only the pack file should be handed to a teammate after the team's privacy review;
the whole run directory must remain private. Sanitization of source exports is
not a public-release or personal-data clearance.

The sealed queue contains guard identifiers and counts, never content or labels.
The original corpus is installed on this Mac, so the seal is a workflow boundary
rather than an access-control boundary. The evaluator must keep sealed labels
apart from routine development. The hash split is not class stratification; class
support and holdout feasibility still require reviewed labels. The review queue
prefers guards with at most eight scoped rows and is not an unbiased population
sample. No accuracy result is claimed.

## Source restrictions

`source_policy.py` fails closed for unknown sources. Scoped and broad share the
same mail snapshot family; broad is an alternative, never an independent test
of scoped. Charlie9 is the declared public sentence actionability baseline.
Parakweet's overlapping conflicting annotations remain comparison-only. The
Durg sample remains quarantined. The `campusmail train` path now loads a single
declared source through the pinned **development** allocation, excluding all
sealed guards and unavailable-text records. It does not pool operational profile
feedback. The actual loader selected 286 weak-labeled scoped academic rows and
2,905 source-labeled Charlie9 rows for development-only training; neither set is
a reviewed benchmark.

## Acceptance and next gate

The reservation builder verified output checksums, all 7,859 guard assignments,
all 17,291 memberships, 189 blinded pack rows and 30 sealed queue guards before
publication. A separate post-publication read produced the same valid counts.
The source-aware development loader read both permitted model sources from the
accepted run; Python compilation and whitespace checks passed. No model was
trained or promoted in this phase.

Next: use the draft [annotation guide](../dataset/ANNOTATION_GUIDE.md) and the
private `artifacts/research/data06-20261028-pilot-v4` forms for two independent
reviews of 50 development notices, adjudicate disagreements, and only then review
sealed examples using the fixed guide. If a class lacks independent support,
report that limitation rather than moving groups or choosing a better-looking
split seed.
