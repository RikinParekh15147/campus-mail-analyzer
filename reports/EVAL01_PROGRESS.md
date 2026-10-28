# EVAL-01 development protocol progress — 28 October 2026

The new `development_protocol.py` freezes a reviewed development selection
against the accepted DATA-05 reservation. It pins the accepted report SHA-256
`07595cb9fe9ac510ea2fee3dd6e7db0f21c70ab37a3342ddb5d0a62ef62ad099`,
checks its sidecar hashes and the DATA-04 membership hash, and maps blinded
review IDs to raw guards only through the private identity map. Reviewed text,
subject, timestamps and context must also match the pinned blinded pack. It rejects
holdout assignments, unknown IDs, unreviewed or single-reviewed classification,
mixed datasets and selections with fewer than two independent guards.

The fold policy is fixed before looking at labels: SHA-256 order on whole
guards, assigned round-robin to up to five folds. The frozen selection records
document-to-guard mapping, fold IDs, source and input hashes, class document
and independent-guard support, per-fold class support and missing classes.
`freeze_development_selection.py` writes the manifest to an owner-only private
directory, and the EVAL-05 runner re-creates it before any research scoring.
This closes the earlier gap where a document's optional legacy
`leakage_group_id` was treated as the DATA-05 split guard.

Read-only verification of the installed accepted reservation matched its
report SHA-256 and reconciled 7,859 allocated guards with 189 blinded
development identities. Four synthetic protocol tests cover map/fold/support
determinism, changed source text and tamper/single-review rejection. The full
portable suite passed 200 tests with one private-data test deselected; lint and
diff checks passed.

EVAL-01 remains open. The DATA-06 pilot still has no completed human forms,
so there is no reviewed class support, no frozen real development folds, and no
evidence that the reserved sealed review set supports all classes. No split
was moved or chosen using labels, and no holdout content was opened for tuning.
The refreshed pilot audit reported 0/50 complete classification reviews for
each reviewer and `human_review_incomplete`.
