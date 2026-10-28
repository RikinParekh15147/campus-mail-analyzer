"""Extraction evaluation, keeping weak-label agreement distinct from gold scores."""

from .nlp import analyze
from .preprocessing import prepare_document


def evaluate_extraction(rows, reviewed_only=False):
    totals = {kind: {"tp": 0, "fp": 0, "fn": 0} for kind in ("dates", "actions")}
    role_correct = role_total = normal_correct = normal_total = documents = reviewed = 0
    for row in rows:
        if reviewed_only and not row.get("human_reviewed"):
            continue
        prepared = prepare_document(row.get("subject", ""), row.get("text", ""))
        if not prepared.body.canonical.strip():
            continue
        documents += 1
        reviewed += bool(row.get("human_reviewed"))
        result = analyze(prepared.body.canonical, prepared.subject.canonical,
                         row.get("sent_at"))
        for kind in ("dates", "actions"):

            def span(item):
                start, end = item.get("start"), item.get("end")
                if not isinstance(start, int) or not isinstance(end, int):
                    return None
                if not 0 <= start <= end <= len(row["text"]):
                    return None
                if kind == "actions":
                    while start < end and row["text"][start].isspace():
                        start += 1
                    while end > start and row["text"][end - 1].isspace():
                        end -= 1
                return start, end

            gold = {span(x): x for x in row.get(kind, []) if span(x) is not None}
            predicted = {span(x): x for x in result[kind] if span(x) is not None}
            overlap = gold.keys() & predicted.keys()
            totals[kind]["tp"] += len(overlap)
            totals[kind]["fp"] += len(predicted.keys() - gold.keys())
            totals[kind]["fn"] += len(gold.keys() - predicted.keys())
            if kind == "dates":
                for key in overlap:
                    if gold[key].get("role") not in (None, "unknown"):
                        role_total += 1
                        role_correct += gold[key]["role"] == predicted[key]["role"]
                    if gold[key].get("normalized_value"):
                        normal_total += 1
                        normal_correct += (
                            str(gold[key]["normalized_value"])[:10]
                            == predicted[key]["normalized"]
                        )
    for scores in totals.values():
        tp, fp, fn = scores["tp"], scores["fp"], scores["fn"]
        scores.update(
            precision=tp / (tp + fp) if tp + fp else None,
            recall=tp / (tp + fn) if tp + fn else None,
            f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        )
    return {
        "documents": documents,
        "human_reviewed_documents": reviewed,
        "label_status": "reviewed_annotations"
        if documents and reviewed == documents
        else "provisional_source_agreement",
        "dates": totals["dates"],
        "actions": totals["actions"],
        "date_role_accuracy": role_correct / role_total if role_total else None,
        "role_evaluated_matches": role_total,
        "normalization_accuracy": normal_correct / normal_total
        if normal_total
        else None,
        "normalization_evaluated_matches": normal_total,
    }
