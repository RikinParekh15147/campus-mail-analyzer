# DATA-06 private review handoff

Use the pinned [annotation guide](ANNOTATION_GUIDE.md) and the two blank forms in
`artifacts/research/data06-20261028-pilot-v4`. Do not edit the guide or blank
forms: their checksums are part of the accepted pilot manifest. Each reviewer
works in a separate copy of their assigned JSONL form, without seeing the
other reviewer's copy. The 30-guard sealed queue is outside this development
pilot. Completed forms and the development pack contain private source material;
keep them in private storage.

Audit the two completed copies:

```bash
.venv/bin/python scripts/audit_annotation_pilot.py \
  --reservation-dir artifacts/research/data05-20261028-reserved-v2 \
  --pilot-dir artifacts/research/data06-20261028-pilot-v4 \
  --reviewer-a /private/path/reviewer_a_completed.jsonl \
  --reviewer-b /private/path/reviewer_b_completed.jsonl \
  --adjudication-queue artifacts/research/data06-disagreements-v1.jsonl
```

The queue path must be new. It is published only after both people complete
classification on all 50 rows. For every disputed document, a third person
fills `adjudicator_id`, a nonempty `reason`, sets `final_decisions_recorded` to
`true`, and fills `decisions` with one object per `disputed_tasks` entry. The
decision object contains the exact fields for that task; classification uses
`primary_category` and `secondary_categories`. The adjudicator may choose a
reviewer's value or a corrected value supported by source evidence. The
adjudicator cannot be either reviewer.

Publish the reviewed **development** pilot after all decisions are complete:

```bash
.venv/bin/python scripts/finalize_annotation_pilot.py \
  --reservation-dir artifacts/research/data05-20261028-reserved-v2 \
  --pilot-dir artifacts/research/data06-20261028-pilot-v4 \
  --reviewer-a /private/path/reviewer_a_completed.jsonl \
  --reviewer-b /private/path/reviewer_b_completed.jsonl \
  --adjudication /private/path/adjudication_completed.jsonl \
  --output-dir artifacts/research/data06-reviewed-development-v1
```

The output directory must be new and private. The command validates all inputs
before publishing `reviewed_development.jsonl` and a checksum/support manifest.
A task is eligible only when both reviewers marked it complete. A reviewed
empty list remains a complete negative; an incomplete empty list stays
unannotated. Every disputed task needs an explicit independent adjudication.
The command cannot create human labels from blank forms or model predictions.
