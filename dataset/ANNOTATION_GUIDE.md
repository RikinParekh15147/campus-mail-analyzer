# Campus mail pilot annotation guide — draft v0.1

This guide governs the DATA-06 **development** pilot. Two reviewers work
independently from `development_pack.jsonl`, then compare decisions and record
adjudication. The 30-guard sealed queue is not part of the pilot. Original weak
labels are hidden from reviewers and must not settle disagreements. Do not copy
the pack or completed forms into Git or a public issue.

## Unit and observation boundary

Annotate one `review_id` at a time. Use its `subject`, `text`, `sent_at` and
available linked `context_review_ids`, `parent_review_id` and relation tokens.
Read linked context only when it was observable by `context_cutoff_at`; later
replies cannot explain an earlier snapshot. An unavailable-text row is context
only and should not receive guessed labels. Treat a quoted prior message as
context, not a fresh obligation, unless the current author explicitly renews
or changes it.

For each task, distinguish **unannotated** (not reviewed), **partial** (some
fields examined), and **complete** (all instances sought, including a genuine
empty list). Never turn a blank list into a negative label unless that task is
marked complete. Record uncertainty in `notes` and use the review state rather
than inventing a date, actor or target.

## Category

Choose one primary category describing the main purpose, plus zero or more
secondary categories only when their independent content is substantial.

| Category | Use for |
|---|---|
| `examinations` | Exam, test, timetable, admit card, result notice |
| `assignments` | Coursework, submission, project deliverable |
| `workshops_events` | Seminar, workshop, club or campus event |
| `placements` | Recruitment, internship, interview, career process |
| `scholarships` | Scholarship, grant or financial-aid opportunity |
| `administration` | Registration, fees, policy, academic administration |
| `course_materials` | Notes, lecture resources or reading materials |
| `nonacademic_other` | No academic or campus task content |

Prefer the notice's actual purpose over sender, template or a single keyword.
For a truly mixed notice, choose the lead purpose and add supported secondary
categories. If no category is defensible, leave classification partial and
explain. Do not copy the source/weak label from another file.

## Actions, dates and links

Mark an action only when a person is asked or expected to do something.
Record the exact evidence span, actor (`student`, `sender`, `recipient`,
`broadcast`, `other`, `unknown`), action type, and status (`required`,
`optional`, `completed`, `negated`, `uncertain`). A corporate sentence's generic
actionability is not proof of a compulsory student task. Separate clauses:
“already registered, but must upload the form” has a completed registration
and a required upload. A quoted request alone is not a current request.

For each explicit date/time, record the exact span, role
(`assignment_deadline`, `registration_deadline`, `event_start`, `event_end`,
`exam_date`, `publication_date`, `other`, `unknown`), ISO normalized value only
when supported, precision and timezone. Anchor relative dates to the original
`sent_at` and its timezone. Missing year or time stays unresolved unless the
notice supplies a defensible reference. Distinguish a deadline from an event
start. For ranges, mark start and end separately. Never create midnight from an
all-day date or a time from an unstated hour.

Give each assignment/event/course/resource a local entity ID and exact evidence
span. Link an action or date to an entity only when the text or permitted
context supports it. Mark updates, corrections and cancellations against the
specific target; similar titles or assignment numbers alone are insufficient.
If two targets are plausible, keep the relation uncertain and explain. A
calendar mutation cannot be justified by an uncertain relation.

For reply-state labels, use the observation cutoff: `needs_reply`,
`waiting_for_other`, `resolved`, `uncertain`, or `not_applicable`. A generic
acknowledgement or shared keyword does not prove a request was resolved.

## Evidence and review procedure

Offsets are zero-based, half-open indexes into the exact `subject` or `text`
field in the development pack. Copy the exact substring as evidence. For an
attachment or table row, keep the available parent/link token and note missing
layout locators. If extraction is unreadable, mark the task partial or
unannotated; do not infer from filename alone.

The blank JSONL forms use `complete_fields` to list only tasks fully inspected:
`classification`, `actions`, `dates`, `entities`, `relationships`,
`reply_state`. For example, a reviewed notice with no action has
`"actions": []` **and** `"actions"` in `complete_fields`; otherwise an empty
array means no annotation was entered. Each action/date item should use the
same field names and enums as `dataset/RESEARCH_SCHEMA.md`, including evidence
as `{"field":"text","start":0,"end":6,"text":"Submit"}`. Replace the
offsets and text with exact values from the reviewed row. Set `reviewer_id` to
the human reviewer identifier. Keep notes for uncertainty and missing context.

1. Each reviewer fills a separate pilot form without seeing the other's form.
2. Compare primary/secondary categories, all complete-task spans, normalized
   dates, actors/statuses and target links. Log every disagreement with both
   initial choices and an adjudicated decision/reason.
3. Revise this guide with a new version when a rule changes. Re-review affected
   examples under the new version. The adjudicator records their ID; a model or
   weak label cannot serve as adjudicator.
4. Report counts of available documents, independent guards, per-class support,
   complete fields and unresolved disagreements. The pilot is development data,
   not a held-out accuracy score.

The work-form generator creates blank forms only; it does not validate or
publish human-reviewed `ResearchDocument` records. DATA-06 remains open until
two actual reviews and adjudication are completed.

After each reviewer saves a separate copy of their form, audit the copies:

```bash
.venv/bin/python scripts/audit_annotation_pilot.py \
  --reservation-dir artifacts/research/data05-20261028-reserved-v2 \
  --pilot-dir artifacts/research/YOUR_PILOT_RUN \
  --reviewer-a /private/path/reviewer_a_completed.jsonl \
  --reviewer-b /private/path/reviewer_b_completed.jsonl
```

The audit checks form identity, separate reviewer IDs, allowed enums, exact
evidence offsets, local entity references, completeness and agreement using the
v2 research contract. It prints aggregate counts only. It never promotes forms
to gold or adjudicates disagreements automatically; the two completed forms and
adjudication record must stay in private storage. The original blank forms are
templates, so auditing them reports `human_review_incomplete`.
