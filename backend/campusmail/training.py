"""Offline research training. Never consumes operational student feedback."""

import hashlib
import json
from pathlib import Path

from .research.files import file_sha256, jsonl_records
from .research.source_policy import (
    SPLIT_POLICY_VERSION, SPLIT_SEED, expected_split, require_source,
)


def load_rows(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        label = d.get("label", d.get("primary_category"))
        if label is None or str(label).lower() in ("null", "unknown", "none"):
            continue
        text = d.get("subject", "") + " " + d.get("text", "")
        if len(text.strip()) < 5:
            continue
        rows.append(
            {
                "text": text,
                "label": str(label),
                "group": d.get("leakage_group_id")
                or d.get("duplicate_group_id")
                or d.get("thread_id")
                or hashlib.sha256(text.encode()).hexdigest(),
            }
        )
    return rows


def load_reserved_development_rows(root, task, source_name, reservation_dir, input_run, component_run):
    """Load weak-label training rows only from the frozen development allocation.

    The reservation is private and pinned to its upstream export. This loader
    deliberately uses one declared source per model; overlapping alternatives
    are never silently pooled. Its labels remain source/weak labels, not gold.
    """
    require_source(source_name, task, "train")
    root = Path(root).resolve()
    reservation_dir = Path(reservation_dir).resolve()
    input_run = Path(input_run).resolve()
    component_run = Path(component_run).resolve()
    report_path = reservation_dir / "reservation_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (report.get("status") != "valid"
        or report.get("policy_version") != SPLIT_POLICY_VERSION
        or report.get("seed") != SPLIT_SEED
        or report.get("data03_run_sha256") != file_sha256(input_run / "run.json")):
        raise ValueError("Research reservation is not pinned to this DATA-03 run")
    allocation_path = reservation_dir / "allocation.jsonl"
    if report["file_sha256"].get("allocation.jsonl") != file_sha256(allocation_path):
        raise ValueError("Research allocation checksum mismatch")
    if report.get("data04_report_sha256") != file_sha256(component_run / "component_report.json"):
        raise ValueError("Research reservation is not pinned to this DATA-04 run")
    membership_path = component_run / "membership.jsonl"
    if report.get("membership_sha256") != file_sha256(membership_path):
        raise ValueError("Research membership checksum mismatch")
    source_manifest = json.loads((root / "research_sources.json").read_text(encoding="utf-8"))
    if report.get("source_manifest_sha256") != file_sha256(root / "research_sources.json"):
        raise ValueError("Research source manifest checksum mismatch")
    source = next((x for x in source_manifest["sources"] if x["name"] == source_name), None)
    if source is None or source["task"] != task:
        raise ValueError("Research source/task mismatch")
    input_report = json.loads((input_run / "run.json").read_text(encoding="utf-8"))
    source_path = input_run / f"{source_name}.v2.jsonl"
    if file_sha256(source_path) != input_report["sources"][source_name]["output_sha256"]:
        raise ValueError("Research source export checksum mismatch")
    allocation = {}
    for line, row, _, error in jsonl_records(allocation_path):
        if (error or row is None
            or row.get("split") != expected_split(row.get("task"), row.get("guard_id"))):
            raise ValueError(f"Invalid allocation line {line}")
        guard = row["guard_id"]
        if guard in allocation:
            raise ValueError("Duplicate guard allocation")
        allocation[guard] = (row["split"], row["task"])
    identities = {}
    for line, row, _, error in jsonl_records(membership_path):
        if error or row is None:
            raise ValueError(f"Invalid membership line {line}")
        if row["source_name"] == source_name:
            guard = row["provisional_split_guard_id"]
            if guard not in allocation or allocation[guard][1] != task or row["task"] != task:
                raise ValueError("Source member has a missing or mismatched split guard")
            key = (row["dataset_id"], row["document_id"])
            if key in identities:
                raise ValueError("Duplicate source membership identity")
            identities[key] = row
    if len(allocation) != report.get("total_guards"):
        raise ValueError("Research allocation is incomplete")
    rows = []
    for line, document, _, error in jsonl_records(source_path):
        if error or document is None:
            raise ValueError(f"Invalid research export line {line}")
        if document["task"] != task or document["dataset_id"] != source["dataset_id"]:
            raise ValueError("Research export source/task mismatch")
        member = identities.pop((document["dataset_id"], document["document_id"]), None)
        if member is None:
            raise ValueError("Research export row has no membership")
        guard = member["provisional_split_guard_id"]
        if guard not in allocation:
            raise ValueError("Research guard is not allocated")
        if allocation[guard][0] != "development" or document.get("text_status", "available") != "available":
            continue
        if document.get("usage_status") == "quarantined":
            continue
        label = document.get("primary_category") if task == "academic" else document.get("actionability_label")
        if label is None:
            continue
        body = f"{document.get('subject', '')} {document['text']}".strip()
        if len(body) < 5:
            continue
        rows.append({"text": body, "label": str(label), "group": guard})
    if identities:
        raise ValueError("Membership has rows absent from research export")
    return rows


def train_models(rows, output):
    import joblib
    import sklearn
    from sklearn.pipeline import make_pipeline
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.naive_bayes import MultinomialNB
    from sklearn.svm import LinearSVC
    from sklearn.dummy import DummyClassifier
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.metrics import (
        accuracy_score,
        f1_score,
        confusion_matrix,
        classification_report,
    )

    if len(rows) < 10 or len({r["label"] for r in rows}) < 2:
        raise ValueError("Need at least ten labeled examples in two classes")
    # Union source groups and exact normalized duplicates before splitting.
    parents = {}

    def find(a):
        parents.setdefault(a, a)
        if parents[a] != a:
            parents[a] = find(parents[a])
        return parents[a]

    texts = {}
    for row in rows:
        group = str(row["group"])
        digest = hashlib.sha256(
            " ".join(row["text"].lower().split()).encode()
        ).hexdigest()
        if digest in texts:
            parents[find(group)] = find(texts[digest])
        else:
            texts[digest] = group
    groups = [find(str(r["group"])) for r in rows]
    if len(set(groups)) < 3:
        raise ValueError("Insufficient independent groups")
    train, test = next(
        GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42).split(
            rows, groups=groups
        )
    )
    x = [r["text"] for r in rows]
    y = [r["label"] for r in rows]
    labels = sorted(set(y))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "records": len(rows),
        "evaluation_scope": "development_only_source_or_weak_labels",
        "sealed_holdout_evaluated": False,
        "train_groups": sorted({groups[i] for i in train}),
        "test_groups": sorted({groups[i] for i in test}),
        "labels": labels,
        "models": {},
        "label_warning": "Source/weak labels; not an independently reviewed gold evaluation",
        "sklearn_version": sklearn.__version__,
        "dataset_sha256": hashlib.sha256(
            json.dumps(rows, sort_keys=True).encode()
        ).hexdigest(),
    }
    pipelines = {}
    for name, estimator in [
        ("naive_bayes", MultinomialNB()),
        ("linear_svm", LinearSVC()),
        ("majority", DummyClassifier(strategy="most_frequent")),
    ]:
        pipeline = make_pipeline(
            TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, max_features=30000),
            estimator,
        )
        pipeline.fit([x[i] for i in train], [y[i] for i in train])
        pred = pipeline.predict([x[i] for i in test])
        report["models"][name] = {
            "accuracy": accuracy_score([y[i] for i in test], pred),
            "macro_f1": f1_score(
                [y[i] for i in test],
                pred,
                labels=labels,
                average="macro",
                zero_division=0,
            ),
            "confusion_matrix": confusion_matrix(
                [y[i] for i in test], pred, labels=labels
            ).tolist(),
            "per_class": classification_report(
                [y[i] for i in test],
                pred,
                labels=labels,
                output_dict=True,
                zero_division=0,
            ),
        }
        pipelines[name] = pipeline
        joblib.dump(pipeline, output / (name + ".joblib"))
    # Predeclared deployment choice; held-out scores are reporting only, not tuning.
    joblib.dump(pipelines["linear_svm"], output / "classifier.joblib")
    report["selected"] = "linear_svm"
    (output / "metrics.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report
