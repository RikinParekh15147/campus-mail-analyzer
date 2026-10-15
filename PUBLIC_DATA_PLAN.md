# Public dataset findings and acquisition plan

Research date: 15 October 2026. Gmail collection is being handled separately. No models were trained in this research step.

## Recommended decision

Use separately curated college notices/Gmail records for academic-category classification. Use the Charlie9 manually verified Enron intent dataset for a sentence-actionability baseline. Keep public-source data, personal project data, synthetic examples, and operational student feedback source-tagged and separate. Public email data alone cannot establish student relevance, enrollment, roll-number identity, or whether a request remains outstanding in a conversation.

## 1. First choice: manually verified sentence actionability

Source: [Charlie9/enron_intent_dataset_verified](https://github.com/Charlie9/enron_intent_dataset_verified).

Downloaded and counted:
- 3,655 records: 1,252 positive and 2,403 negative.
- Positive criteria cover genuine actions/questions and certain upcoming meeting/event information.
- The maintainer describes manual verification by one individual. This is an existing source annotation, not a project-reviewed gold standard.
- Repository declares MIT; it derives from Parakweet/Enron. Preserve source LICENSE/README and upstream attribution; do not imply the original email content originated with this maintainer.

Appropriate use: train/compare TF-IDF + Naive Bayes and linear SVM for sentence actionability, optionally assisting action extraction.

Limitations: corporate domain; sentence/phrase examples, not full conversations; positive intent does not mean a reply is currently outstanding; source assumptions omit certain attachment/CC relevance and are not identical to our application's rules. Do not map the binary label directly to all academic categories or reply-state labels.

Local data: `dataset/public/raw/charlie9_verified/` and `dataset/public/normalized/charlie9_verified.jsonl`.

## 2. Original source / alternative baseline: Parakweet

Source: [ParakweetLabs/EmailIntentDataSet](https://github.com/ParakweetLabs/EmailIntentDataSet).

Downloaded TXT resources and retained source README/LICENSE:
- 4,649 labeled rows across the supplied training and test resources.
- 2,028 positive and 2,621 negative.
- 4,645 distinct texts after lowercase/whitespace normalization.
- Repository declares Apache-2.0.

Measured overlap with Charlie9: 3,644 distinct normalized texts. These datasets are alternative annotations of substantially overlapping examples, not independent datasets. Do not train on one and claim evaluation on the other is held out. If comparing annotation schemes, define one split over their combined duplicate groups first and evaluate each scheme explicitly.

Local data: `dataset/public/raw/parakweet/` and `dataset/public/normalized/parakweet.jsonl`. Original train/test assignment is preserved in the normalized records. Additional near-duplicate/template checks are needed before final model evaluation.

## 3. University corpus candidate: Durg University notices

Sources:
- [DURG-UV-NOTICES metadata](https://huggingface.co/datasets/sameerbanchhor/DURG-UV-NOTICES)
- [University PDF archive dataset](https://huggingface.co/datasets/sameerbanchhor/durg-university-notices)
- [Metadata file inspected](https://huggingface.co/datasets/sameerbanchhor/DURG-UV-NOTICES/resolve/main/structured_data.json)

Initial inspection downloaded the approximately 1.46 MB catalogue. Subsequent authorized acquisition downloaded the preserved 2.79 GB PDF archive and verified its publisher SHA-256. Acquisition outputs and sample details are recorded in `dataset/public/DOWNLOAD_REPORT.md`. The catalogue has 2,476 records containing titles, PDF URLs, publication dates, language tags, categories and some course/subject metadata.

Actual catalogue category counts:

| Existing category | Count |
|---|---:|
| Result | 1,426 |
| Other | 369 |
| Notification | 294 |
| Syllabus | 123 |
| Admission | 109 |
| Time Table | 88 |
| Admit Card | 38 |
| Merit List | 29 |

Language tags: English 1,785; Hindi 576; Mixed 115. These are supplied metadata labels, not a verified assessment of the linked PDF body language/readability.

The inspected Hugging Face metadata provides no dataset card/license, and category annotation provenance is unclear. Catalogue is quarantined, not marked training-ready. File availability and metadata tags are not proof of a reusable labeled English-notice corpus.

If usage/provenance are established, inspect a small English-tagged PDF sample, count readable vs scanned documents, verify titles against actual bodies, and annotate under our taxonomy. Category mapping requires review: e.g., Time Table may relate to examinations or classes; Result often belongs to examinations; generic Notification cannot be mapped without its body. Exclude Hindi/mixed content from the English baseline unless readable English content is separately identified. Results dominate, so avoid letting this source overwhelm minority classes. Do not confuse the 2,476 metadata entries with the separate PDF archive's advertised 2,376 rows; coverage differs and requires reconciliation.

Local catalogue: `dataset/public/quarantine/durg_notice_catalogue.json`.

## 4. Best primary academic material: official institutional sources

Sources inspected:
- [IIT Gandhinagar announcements](https://iitgn.ac.in/news_announcement)
- [IIT Gandhinagar student-organized events](https://students.iitgn.ac.in/eii/events.html)
- [IIT Gandhinagar CSE deadlines](https://cse.iitgn.ac.in/updates/deadlines/)
- [PDEU research/financial assistance](https://pdeu.ac.in/research)
- [PDEU admissions/scholarships](https://www.pdeu.ac.in/admissions)

These are source material, not existing project-category labels. Use announcements and their source PDFs, preserve publication/source URLs, and annotate categories/date roles/actions with AI-assisted labeling and human review. Check applicable reuse terms before distributing full-text datasets. General policies, admission pages and retrospective news are not equivalent to time-sensitive student email notices, so record source type and document genre rather than pretending all records are inbox messages.

Prefer multiple institutions and avoid collecting only admission/result notices. Assignments and marks matching will still rely heavily on the user's designated research email collection and carefully constructed fixtures.

Initial target, subject to availability: 150–300 distinct English notices across institutions plus the separately collected Gmail examples. This is a target, not a claim of current collection. Keep institution/template/event-update families together in splits.

## 5. Additional sources, lower priority

### Full CMU Enron corpus

[Official CMU source](https://www.cs.cmu.edu/~enron/) provides approximately 0.5 million corporate messages, without attachments in that version. Useful later for parser/thread stress tests and manually annotated request-state examples. It lacks our college categories and ongoing-reply-state ground truth; a huge download adds little to the initial notice experiment. Full archive was not downloaded.

### Synthetic email intent sample

[elenigkove/Email_Intent_Classification](https://huggingface.co/datasets/elenigkove/Email_Intent_Classification) explicitly describes GPT-4-generated/annotated examples and fewer than 1,000 records. The inspected metadata does not declare a license. Its card's description of category count/names is also incomplete. Keep as a possible synthetic smoke-test candidate; not chosen as primary training or real-data evaluation. Files were not downloaded.

## 6. What public data does not yet cover

No verified, fully matched public dataset was established in this search for all of: enrolled-course relevance, personal importance, cross-email assignment/PDF relationships, outstanding reply state, student-specific marks, and timetable-plus-holiday conflict resolution.

Use separate datasets/tasks:

| Task | Preferred source and preparation |
|---|---|
| Academic categories | Designated Gmail + official university notice material; AI provisional labels plus review |
| Actionability | Charlie9 binary sentences; domain-check on reviewed academic examples |
| Dates and deadline roles | Manually annotate a subset of real notices |
| Reply-state tracking | Annotated complete time-specific threads; sentence intent alone is insufficient |
| Resource association | Gmail threads/attachments + explicit cross-message fixtures |
| Identity and marks | Designated anonymized records + negative/ambiguous fixtures |
| Personal importance | Personal feedback, never pooled into shared training |
| Calendar/holiday logic | Deterministic fixtures and validated import schemas |

## 7. Acquisition outputs and validation

Saved raw source resources, README/LICENSE files, normalized sentence JSONL, and `dataset/public/manifest.json` with URLs, byte counts, hashes, actual label counts and license/provenance notes.

Normalization preserves source file/line, original split where present, task identity and normalized duplicate-group hashes. Labels were imported from sources, not AI-reinvented. `human_reviewed_by_project` is false. No public material was merged with private Gmail data and no trained model/performance claim was generated.

Next implementation step: inspect actionability class balance and annotation suitability; prepare grouped training splits; independently curate/annotate the academic-notice dataset when the personal export becomes available. Do not automatically combine Charlie9, Parakweet and full Enron as independent evaluation sources.
