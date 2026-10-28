"""Completeness-aware component scoring for reviewed research documents."""

from collections import Counter, defaultdict

from ..models import CATEGORIES
from .contracts import ResearchDocument


def _score(tp, fp, fn):
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
    }


def _prediction_spans(document, entries, task):
    if not isinstance(entries, list):
        raise ValueError(f"Predicted {task} must be a list")
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"Predicted {task} item must be an object")
        field = entry.get("field", "text")
        source = getattr(document, field, None) if field in {"text", "subject"} else None
        start, end = entry.get("start"), entry.get("end")
        if (source is None or type(start) is not int or type(end) is not int
            or not 0 <= start < end <= len(source)
            or entry.get("text") != source[start:end]):
            raise ValueError(f"Invalid predicted {task} evidence span")
        result.append((field, start, end, entry))
    return result


def _gold_spans(entries):
    return [(item.evidence.field, item.evidence.start, item.evidence.end, item)
            for item in entries]


def _iou(left, right):
    if left[0] != right[0]:
        return 0.0
    overlap = max(0, min(left[2], right[2]) - max(left[1], right[1]))
    union = max(left[2], right[2]) - min(left[1], right[1])
    return overlap / union if union else 0.0


def _match(gold, predicted, threshold):
    """Greedy one-to-one maximum-overlap matching with deterministic ties."""
    candidates = [
        (-_iou(g, p), gi, pi)
        for gi, g in enumerate(gold) for pi, p in enumerate(predicted)
        if _iou(g, p) >= threshold
    ]
    used_gold, used_pred, matches = set(), set(), []
    for _, gi, pi in sorted(candidates):
        if gi not in used_gold and pi not in used_pred:
            used_gold.add(gi)
            used_pred.add(pi)
            matches.append((gi, pi))
    return matches


def _normalized_prediction(entry):
    value = entry.get("normalized_value", entry.get("normalized"))
    return value if isinstance(value, str) else None


def evaluate_reviewed_components(pairs):
    """Score (v2 gold, prediction) pairs; skip only explicitly unreviewed tasks.

    Predictions use the deployed `analyze` shape plus optional `field`, `actor`,
    `action_status` and `normalized_value` fields. Invalid evidence is an error,
    never a silently discarded prediction. No score is called a sealed-test score
    by this function; the caller must enforce partition custody.
    """
    category = Counter()
    category_by_class = defaultdict(Counter)
    span_counts = {kind: Counter() for kind in ("dates", "actions")}
    overlap_counts = {kind: Counter() for kind in ("dates", "actions")}
    role = Counter()
    role_joint = Counter()
    action_status = Counter()
    action_actor = Counter()
    normalization = Counter()
    eligible = Counter()
    excluded = Counter()
    documents = 0
    for raw_document, prediction in pairs:
        document = (raw_document if isinstance(raw_document, ResearchDocument)
                    else ResearchDocument.model_validate(raw_document))
        if not isinstance(prediction, dict):
            raise ValueError("Prediction must be an object")
        if document.data_origin == "synthetic" or document.usage_status == "quarantined":
            excluded["source_policy"] += 1
            continue
        documents += 1
        if document.task == "academic" and document.gold_eligible("classification"):
            eligible["classification"] += 1
            predicted_category = prediction.get("category")
            if predicted_category not in CATEGORIES:
                raise ValueError("Predicted category is missing or outside taxonomy")
            gold_category = document.primary_category
            category["total"] += 1
            category["correct"] += predicted_category == gold_category
            for label in CATEGORIES:
                if gold_category == label and predicted_category == label:
                    category_by_class[label]["tp"] += 1
                elif gold_category == label:
                    category_by_class[label]["fn"] += 1
                elif predicted_category == label:
                    category_by_class[label]["fp"] += 1
            category_by_class[gold_category]["support"] += 1
        else:
            excluded["classification_unreviewed_or_nonacademic"] += 1
        for kind in ("dates", "actions"):
            proposed = prediction.get(kind, [])
            if kind == "dates":
                subject_proposed = prediction.get("subject_dates", [])
                if not isinstance(proposed, list) or not isinstance(subject_proposed, list):
                    raise ValueError("Predicted dates must be lists")
                proposed = proposed + subject_proposed
            predicted = _prediction_spans(document, proposed, kind)
            if not document.gold_eligible(kind):
                excluded[f"{kind}_unreviewed"] += 1
                continue
            eligible[kind] += 1
            gold = _gold_spans(getattr(document, kind))
            exact = _match(gold, predicted, 1.0)
            partial = _match(gold, predicted, 0.5)
            for bucket, matches in ((span_counts[kind], exact),
                                    (overlap_counts[kind], partial)):
                bucket["tp"] += len(matches)
                bucket["fp"] += len(predicted) - len(matches)
                bucket["fn"] += len(gold) - len(matches)
            if kind == "dates":
                matched_gold = {gi for gi, _ in exact}
                matched_pred = {pi for _, pi in exact}
                role_joint["fn"] += len(gold) - len(matched_gold)
                role_joint["fp"] += len(predicted) - len(matched_pred)
                for gi, pi in exact:
                    original, proposal = gold[gi][3], predicted[pi][3]
                    role["total"] += 1
                    if proposal.get("role") == original.role:
                        role["correct"] += 1
                        role_joint["tp"] += 1
                    else:
                        role_joint["fp"] += 1
                        role_joint["fn"] += 1
                    if original.normalized_value is not None:
                        normalization["total"] += 1
                        normalization["correct"] += (
                            _normalized_prediction(proposal) == original.normalized_value
                        )
            else:
                for gi, pi in exact:
                    original, proposal = gold[gi][3], predicted[pi][3]
                    action_status["total"] += 1
                    action_status["correct"] += (
                        proposal.get("action_status", proposal.get("status"))
                        == original.action_status
                    )
                    action_actor["total"] += 1
                    action_actor["correct"] += proposal.get("actor") == original.actor
    class_metrics = {
        label: {**_score(counts["tp"], counts["fp"], counts["fn"]),
                "support": counts["support"]}
        for label, counts in category_by_class.items()
    }
    supported_f1 = [values["f1"] for values in class_metrics.values()
                    if values["support"] and values["f1"] is not None]
    return {
        "documents_seen": documents,
        "eligible_documents": dict(eligible),
        "excluded": dict(excluded),
        "classification": {
            "accuracy": category["correct"] / category["total"] if category["total"] else None,
            "correct": category["correct"], "total": category["total"],
            "macro_f1_supported_classes": sum(supported_f1) / len(supported_f1) if supported_f1 else None,
            "classes": class_metrics,
            "unsupported_classes": [label for label in CATEGORIES if category_by_class[label]["support"] == 0],
        },
        "strict_spans": {
            kind: _score(counts["tp"], counts["fp"], counts["fn"])
            for kind, counts in span_counts.items()
        },
        "diagnostic_overlap_iou_0_5": {
            kind: _score(counts["tp"], counts["fp"], counts["fn"])
            for kind, counts in overlap_counts.items()
        },
        "date_role_exact_span_accuracy": role["correct"] / role["total"] if role["total"] else None,
        "date_role_exact_span_support": role["total"],
        "date_role_and_span": _score(role_joint["tp"], role_joint["fp"], role_joint["fn"]),
        "date_normalization_exact_span_accuracy": normalization["correct"] / normalization["total"] if normalization["total"] else None,
        "date_normalization_exact_span_support": normalization["total"],
        "action_status_exact_span_accuracy": action_status["correct"] / action_status["total"] if action_status["total"] else None,
        "action_status_exact_span_support": action_status["total"],
        "action_actor_exact_span_accuracy": action_actor["correct"] / action_actor["total"] if action_actor["total"] else None,
        "action_actor_exact_span_support": action_actor["total"],
    }
