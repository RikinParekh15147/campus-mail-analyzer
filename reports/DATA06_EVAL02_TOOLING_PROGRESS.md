# DATA-06 pilot and EVAL-02 scoring preparation — 28 October 2026

The accepted private pilot is `artifacts/research/data06-20261028-pilot-v4`.
Its manifest pins the DATA-05 development pack and guide hashes. It selects 50
available-text notices from 50 independent development guards: 16 linked,
three long, 12 short and 19 ordinary. Two separate blank forms were generated.

`scripts/audit_annotation_pilot.py` checks form identity, guide/pack integrity,
distinct human reviewer IDs, task completeness, permitted labels, exact evidence
offsets and local references through the v2 contract. It reports agreement only
for tasks both reviewers marked complete and can write a private disagreement
queue after both complete classification. It cannot adjudicate on behalf of a
human or convert unreviewed forms to gold.

`research/metrics.py` now has a completeness-aware scoring core for reviewed v2
documents: academic category support/accuracy/macro-F1, strict one-to-one span
precision/recall/F1, diagnostic one-to-one overlap, joint date role/span F1,
conditional date normalization and action status/actor agreement. Invalid
predicted evidence raises an error. Synthetic and quarantined rows are excluded;
unreviewed tasks do not become negative examples. This scoring core is not yet
an accepted EVAL-02 run or an end-to-end runtime evaluator.

The initial pilot audit returned `human_review_incomplete`: zero completed
classification reviews for either person, zero comparable tasks, no adjudication
and no gold-eligible rows. Python compilation and whitespace checks passed.
DATA-06 and EVAL-02 remain unchecked. No reviewed model score or accuracy improvement is
claimed. Next input is two genuinely completed reviewer forms and an adjudicator
for disagreements; after that, expand reviewed development labels and run the
baseline on the frozen development partition.

## Development-only weak-label model check

The reserved loader supplied 286 scoped academic rows and 2,905 Charlie9
actionability rows. Existing NB, linear SVM and majority recipes trained on
those development rows and wrote local candidates to ignored
`artifacts/research/data05-20261028-weak-baselines/`. The internal development
split produced SVM macro-F1 0.615 academic and 0.793 actionability **against
source/weak labels**. These figures are not reviewed accuracy, are not a
sealed-test result and are not comparable to the historical split's scores.

A fabricated assignment notice was classified as `examinations` by the academic
candidate. The candidates were therefore kept outside the app's active
`artifacts/models/` path. `campusmail doctor` subsequently reported `rules_only`
with no active model. EVAL-06 and CLS-04 remain open until reviewed development
labels can support a promotion decision.
