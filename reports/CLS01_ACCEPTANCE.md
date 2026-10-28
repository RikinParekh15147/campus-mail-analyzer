# CLS-01 sparse feature candidates — 28 October 2026

`classification.py` provides versioned, independently selectable word TF-IDF,
character `char_wb` TF-IDF, subject-word and body-word channels. The feature
union is unfitted when built; each vectorizer learns its vocabulary only when
the caller fits that union inside a training fold. Word features retain cues
such as negation, course identifiers and explicit years; character features
give a bounded alternative for spelling and code variants. The shared
preprocessing version is required for subject/body channel rows.

Both training row loaders can opt into separate source-aligned subject/body
fields while preserving the existing default row shape and deployed training
recipe. The four predeclared variants support word, word+character,
subject+body and all-channel ablations. Fixture tests confirm a held-out token
never enters fitted vocabulary, channel vocabularies remain separate, and
missing/stale channel contracts fail before an experiment.

The 270-test portable suite passed, one private-data test was deselected, and
lint passed. No corpus run, model selection or accuracy gain is claimed.
CLS-02 owns a bounded comparison on identical development folds after the
DATA-06 reviewed labels and EVAL-06 baseline exist.
