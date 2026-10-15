# Preliminary research results

These are source/weak-label agreement measurements, not a human-reviewed college-notice benchmark. No operational student feedback enters this training.

| Task | Model | Accuracy | Macro F1 |
|---|---|---:|---:|
| academic (438 records) | naive_bayes | 0.339 | 0.226 |
| academic (438 records) | linear_svm | 0.512 | 0.481 |
| academic (438 records) | majority | 0.157 | 0.034 |
| actionability (3655 records) | naive_bayes | 0.720 | 0.614 |
| actionability (3655 records) | linear_svm | 0.817 | 0.802 |
| actionability (3655 records) | majority | 0.628 | 0.386 |

## Extraction agreement

Evaluated 439 scoped source documents; 0 marked human-reviewed.

| Extraction | Precision | Recall | F1 |
|---|---:|---:|---:|
| dates | 0.839 | 0.222 | 0.351 |
| actions | 0.409 | 0.180 | 0.250 |

Date-role agreement on matched dates: 0.24315068493150685. Normalization agreement on matched, normalized source dates: 0.9923809523809524.

## Interpretation and next research work

- The scoped dataset has sparse classes and provisional annotations. Public sentence actionability is a different corporate-domain task, not outstanding-thread-state ground truth.
- Exact duplicate/source groups stay together. Charlie9 is not mixed with the overlapping Parakweet corpus. Sentence-level public data lacks complete original thread grouping.
- SVM is a predeclared deployment choice; these held-out scores are not used for repeated tuning.
- Date roles are evaluated separately on correctly located date mentions. Action sentence spans normalize surrounding whitespace only. Missing gold annotations can make valid extractions appear as false positives.
- Review a separate real-data evaluation set before presenting gold accuracy. Inspect sparse categories, ambiguous numeric dates, quoted history, table layouts, and context-dependent actions.
- Unknown-license university PDFs remain outside training. Synthetic tests verify application behavior and are not counted as real-data model evaluation.
