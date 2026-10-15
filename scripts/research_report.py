from pathlib import Path
import json
from campusmail.evaluation import evaluate_extraction

root = Path(__file__).resolve().parents[1]
output = root / "reports"
output.mkdir(exist_ok=True)
rows = [
    json.loads(line)
    for line in (root / "dataset/mail/scoped_run/sanitized/documents.jsonl")
    .read_text(encoding="utf-8")
    .splitlines()
]
extraction = evaluate_extraction(rows)
(root / "artifacts/models/extraction_metrics.json").write_text(
    json.dumps(extraction, indent=2) + "\n"
)
lines = [
    "# Preliminary research results",
    "",
    "These are source/weak-label agreement measurements, not a human-reviewed college-notice benchmark. No operational student feedback enters this training.",
    "",
    "| Task | Model | Accuracy | Macro F1 |",
    "|---|---|---:|---:|",
]
for task in ("academic", "actionability"):
    report = json.loads((root / "artifacts/models" / task / "metrics.json").read_text())
    for model, score in report["models"].items():
        lines.append(
            f"| {task} ({report['records']} records) | {model} | {score['accuracy']:.3f} | {score['macro_f1']:.3f} |"
        )
lines += [
    "",
    "## Extraction agreement",
    "",
    f"Evaluated {extraction['documents']} scoped source documents; {extraction['human_reviewed_documents']} marked human-reviewed.",
    "",
    "| Extraction | Precision | Recall | F1 |",
    "|---|---:|---:|---:|",
]
for kind in ("dates", "actions"):
    s = extraction[kind]
    fmt = lambda value: "Not measured" if value is None else f"{value:.3f}"
    lines.append(
        f"| {kind} | {fmt(s['precision'])} | {fmt(s['recall'])} | {fmt(s['f1'])} |"
    )
lines += [
    "",
    f"Date-role agreement on matched dates: {extraction['date_role_accuracy']}. Normalization agreement on matched, normalized source dates: {extraction['normalization_accuracy']}.",
    "",
    "## Interpretation and next research work",
    "",
    "- The scoped dataset has sparse classes and provisional annotations. Public sentence actionability is a different corporate-domain task, not outstanding-thread-state ground truth.",
    "- Exact duplicate/source groups stay together. Charlie9 is not mixed with the overlapping Parakweet corpus. Sentence-level public data lacks complete original thread grouping.",
    "- SVM is a predeclared deployment choice; these held-out scores are not used for repeated tuning.",
    "- Date roles are evaluated separately on correctly located date mentions. Action sentence spans normalize surrounding whitespace only. Missing gold annotations can make valid extractions appear as false positives.",
    "- Review a separate real-data evaluation set before presenting gold accuracy. Inspect sparse categories, ambiguous numeric dates, quoted history, table layouts, and context-dependent actions.",
    "- Unknown-license university PDFs remain outside training. Synthetic tests verify application behavior and are not counted as real-data model evaluation.",
]
(output / "PRELIMINARY_RESULTS.md").write_text(
    "\n".join(lines) + "\n", encoding="utf-8"
)
print(json.dumps(extraction))
