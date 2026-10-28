# PIPE-02 shared preprocessing acceptance — 28 October 2026

`preprocessing.py` defines `source-blocks-v1`: separate subject, body and
indexed attachment blocks; original and canonical text; authored, quoted,
reply-history and signature regions; and an identity canonical-to-source span
map. Masking preserves text length and newlines. The original blocks remain
available for contextual linking, while masked regions cannot supply extracted
evidence. An attachment analyzed as a child message retains its own source
body and parent context in the existing runtime path.

Runtime analysis, training row loaders, extraction evaluation and the rules
experiment now use this contract. Model input has the same subject/body
construction in training and runtime. Quote-only bodies are excluded from
training and extraction evaluation, matching the engine's no-authored-text
path. Training reports and research run identities record the preprocessing
version, and the experiment code digest includes the new module. Any model
trained under the previous raw-concatenation path must be rebuilt before use;
OPS-01 owns model-bundle compatibility checks.

Synthetic acceptance checks cover region boundaries, offset preservation,
masked-span rejection, attachment indexing, idempotence, model-input parity,
quote-only exclusion and the experiment version. The portable suite passed
258 tests with one private-data test deselected. Private reviewed accuracy
remains unmeasured; this change is a contract and safety improvement.
