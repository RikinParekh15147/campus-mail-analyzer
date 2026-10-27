# DATA-04 leakage components — 27 October 2026

Completed against the pinned, validated DATA-03 run
`data03-20261027-verified`. The accepted component run is the ignored local
artifact `artifacts/research/data04-20261027-short`. No raw message body or
private member list is committed; the report here contains aggregates only.

## Measured outcome

| Measure | Value |
|---|---:|
| Source records assigned exactly once | 17,291 |
| Academic records / hard components | 8,987 / 3,435 |
| Actionability records / hard components | 8,304 / 4,633 |
| Total trusted components | 8,068 |
| Provisional split guards including unresolved legacy groups | 7,859 |
| Existing legacy leakage groups spanning trusted components | 124 |
| New verified near-duplicate joins | 139 |
| Cross-snapshot shared source identities linked | 575 (all scoped records) |
| Independent source-reference edges checked | 48,995 |
| Independent postcheck errors | 0 |

The near index covered 6,364 long-text word-shingle records and 4,919 short-text
character-shingle records. It excluded 1,633 inputs below 45 characters; their
exact matches and declared relations remain grouped. There were no skipped long
texts or oversized candidate buckets. It verified 2,689 candidate pairs after
preexisting groups and length gates; 139 new joins passed exact Jaccard checks.
Near joins by source pair: broad/broad 111, scoped/scoped four, Charlie9/Charlie9
17, Charlie9/Parakweet five, Parakweet/Parakweet one, Durg/Durg one. Thirteen
new near joins connect different weak/source labels. Those labels remain
unresolved and require review; no majority vote or label rewrite occurred.

The single trusted component above the 100-record audit threshold has 142 rows:
71 scoped and 71 broad representations of **the same provider thread**. It
contains 44 message rows and 98 attachment rows and spans about one month. Its
size is explained by the duplicated snapshot and thread structure, not by an
unbounded subject-key merge. No public actionability component exceeds four
rows.

Legacy grouping generated from bare subject matches would overmerge: one
114-record provisional guard contains 43 broad-mail threads spanning roughly
three years. The accepted component policy keeps those as reviewable soft links.
All 124 old groups spanning hard components are recorded privately; the
provisional guard manifest keeps them together for any later split until
adjudicated. The largest guard sizes are 142, 114 and 95 academic rows.

## Label conflicts and split feasibility

- Same original mail identity has **128** different weak category labels between
  the scoped and broad snapshots. These rows still share a component.
- Identical normalized bodies carry differing asserted categories in **15**
  academic groups. Charlie9 and Parakweet alternatives contribute **749**
  exact-body actionability label conflict groups. Source labels are not project
  reviewed gold and were not corrected by grouping.
- In scoped mail, usable labels have limited independent support: assignments
  25 rows/17 trusted components; scholarships 17/14; nonacademic-other two/two.
  Those counts do not justify a reliable per-class sealed-test score without
  reviewed examples and uncertainty reporting.
- Source boundaries remain explicit. The quarantined Durg sample was grouped
  for leakage accounting but is not an approved training source. Academic and
  actionability examples never join the same component.

## Verification and reproducibility

The run records the pinned DATA-03 manifest and run checksums, output hashes,
Python/NumPy/platform versions, Git revision and implementation file hashes.
Its membership SHA-256 is
`26ef07b07020553080a83b7d9f8ed44f5160a421e6346cb552259ccf663f8e21`.
The near-edge and soft-review sidecars also have recorded hashes. The
independent postcheck found zero missing members, split edges, cross-task
components or output-hash mismatches across 17,291 records and 48,995 references.

Adversarial fixture tests cover threads, unreadable attachments, context and
update edges, cross-snapshot identity, exact and long/short near duplicates,
conflicting labels, task/ID namespaces, giant-component reporting, legacy
subject-key overmerging, input tampering and corrupted output membership.

Reproduce with a new output directory:

```bash
.venv/bin/python scripts/build_leakage_components.py \
  --input-run artifacts/research/data03-20261027-verified \
  --output-dir artifacts/research/NEW_DATA04_RUN
```

No train/development/test split was assigned here. DATA-05 must use
`provisional_split_guard_id` until soft links have been adjudicated, then reserve
whole groups with class-support checks. Reviewed labels and a sealed test remain
DATA-06–08 work; these grouping counts are not accuracy measurements.
