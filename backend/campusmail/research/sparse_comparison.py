"""Bounded, group-fold sparse-model comparison; no artifact promotion."""

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from ..classification import FEATURE_VARIANTS, build_features, validate_feature_rows
from ..preprocessing import PREPROCESSING_VERSION, prepare_document
from .contracts import ResearchDocument
from .development_protocol import verify_development_selection
from .files import file_sha256, jsonl_records


COMPARISON_VERSION = "sparse-comparison-v1"
COURSE_CODE = re.compile(r"\b[A-Z]{2,5}[- ]?\d{3}\b", re.I)


@dataclass(frozen=True)
class Candidate:
    name: str
    feature: str
    estimator: str
    class_weight: str | None = None
    mask_identifiers: bool = False


CANDIDATES = (
    Candidate("majority_word", "word", "majority"),
    Candidate("naive_bayes_word", "word", "multinomial_nb"),
    Candidate("linear_svm_word", "word", "linear_svm"),
    Candidate("linear_svm_word_char", "word_char", "linear_svm"),
    Candidate("linear_svm_word_char_balanced", "word_char", "linear_svm", "balanced"),
    Candidate("linear_svm_word_char_masked", "word_char", "linear_svm",
              mask_identifiers=True),
    Candidate("logistic_word_char", "word_char", "logistic_regression"),
    Candidate("complement_nb_word_char", "word_char", "complement_nb"),
    Candidate("linear_svm_subject_body", "subject_body", "linear_svm"),
)


def _masked(rows):
    return [{**row, **{field: COURSE_CODE.sub("COURSECODE", row[field])
                      for field in ("text", "subject_text", "body_text")}}
            for row in rows]


def _estimator(candidate):
    from sklearn.dummy import DummyClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.naive_bayes import ComplementNB, MultinomialNB
    from sklearn.svm import LinearSVC

    if candidate.estimator == "majority":
        return DummyClassifier(strategy="most_frequent")
    if candidate.estimator == "multinomial_nb":
        return MultinomialNB()
    if candidate.estimator == "complement_nb":
        return ComplementNB()
    if candidate.estimator == "linear_svm":
        return LinearSVC(C=1.0, class_weight=candidate.class_weight,
                         random_state=17)
    if candidate.estimator == "logistic_regression":
        return LogisticRegression(C=1.0, max_iter=1000, random_state=17)
    raise ValueError("Unknown candidate estimator")


def compare_sparse_models(rows, guard_folds):
    """Score every predeclared candidate on identical, caller-frozen folds.

    Rows must be independently reviewed before results can be called accuracy.
    This function never writes or selects a model; it records paired predictions.
    """
    from sklearn.metrics import f1_score
    from sklearn.pipeline import Pipeline

    if not isinstance(rows, list) or not rows or not isinstance(guard_folds, dict):
        raise ValueError("Comparison needs rows and frozen guard folds")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Comparison rows must be objects")
    ids = [row.get("document_id") for row in rows]
    if any(not isinstance(value, str) or not value for value in ids) or \
            len(ids) != len(set(ids)):
        raise ValueError("Comparison document IDs must be unique")
    groups = {row.get("group") for row in rows}
    if (any(not isinstance(group, str) or not group for group in groups)
        or groups != set(guard_folds)
        or any(type(fold) is not int or fold < 0 for fold in guard_folds.values())):
        raise ValueError("Comparison guards do not match frozen folds")
    fold_ids = sorted(set(guard_folds.values()))
    if fold_ids != list(range(len(fold_ids))) or len(fold_ids) < 2:
        raise ValueError("Comparison requires contiguous independent folds")
    if any(row.get("preprocessing_version") != PREPROCESSING_VERSION
           or not isinstance(row.get("label"), str) or not row["label"]
           for row in rows):
        raise ValueError("Comparison rows need current preprocessing and labels")
    if len({row["label"] for row in rows}) < 2:
        raise ValueError("Comparison needs at least two classes")
    for row in rows:
        validate_feature_rows([row], FEATURE_VARIANTS["word"])
    for fold in fold_ids:
        train = [row for row in rows if guard_folds[row["group"]] != fold]
        test = [row for row in rows if guard_folds[row["group"]] == fold]
        if not test or len({row["label"] for row in train}) < 2:
            raise ValueError("Fold lacks test documents or two training classes")
    labels = sorted({row["label"] for row in rows})
    fold_membership = {row["document_id"]: guard_folds[row["group"]] for row in rows}
    result = {
        "comparison_version": COMPARISON_VERSION,
        "preprocessing_version": PREPROCESSING_VERSION,
        "folds": fold_membership,
        "support": {"documents": len(rows), "guards": len(groups),
                    "classes": dict(sorted(Counter(row["label"] for row in rows).items()))},
        "candidates": {},
        "selection": None,
    }
    for candidate in CANDIDATES:
        spec = FEATURE_VARIANTS[candidate.feature]
        predictions = {}
        for fold in fold_ids:
            train = [row for row in rows if guard_folds[row["group"]] != fold]
            test = [row for row in rows if guard_folds[row["group"]] == fold]
            if candidate.mask_identifiers:
                train, test = _masked(train), _masked(test)
            validate_feature_rows(train, spec)
            model = Pipeline([
                ("features", build_features(spec)),
                ("classifier", _estimator(candidate)),
            ])
            model.fit(train, [row["label"] for row in train])
            predicted = model.predict(test)
            predictions.update({row["document_id"]: str(label)
                                for row, label in zip(test, predicted)})
        ordered = sorted(rows, key=lambda row: row["document_id"])
        truth = [row["label"] for row in ordered]
        proposed = [predictions[row["document_id"]] for row in ordered]
        result["candidates"][candidate.name] = {
            "feature": candidate.feature, "estimator": candidate.estimator,
            "class_weight": candidate.class_weight,
            "mask_identifiers": candidate.mask_identifiers,
            "macro_f1": f1_score(truth, proposed, labels=labels,
                                 average="macro", zero_division=0),
            "predictions": {row["document_id"]: predictions[row["document_id"]]
                            for row in ordered},
        }
    return result


def compare_reviewed_development(input_path, manifest_path, reservation_dir,
                                 *, fixture_mode=False):
    """Use the verified DATA-05 selection; never read sealed-test documents."""
    manifest = verify_development_selection(input_path, manifest_path, reservation_dir,
                                            fixture_mode=fixture_mode)
    rows = []
    for line, value, _, error in jsonl_records(input_path):
        if error or value is None:
            raise ValueError(f"Invalid reviewed JSONL at line {line}")
        document = ResearchDocument.model_validate(value)
        prepared = prepare_document(document.subject, document.text)
        if not prepared.body.canonical.strip():
            raise ValueError("Reviewed document has empty canonical body")
        rows.append({
            "document_id": document.document_id,
            "group": manifest["document_guards"][document.document_id],
            "label": document.primary_category,
            "text": prepared.classifier_text,
            "subject_text": prepared.subject.canonical,
            "body_text": prepared.body.canonical,
            "preprocessing_version": PREPROCESSING_VERSION,
        })
    if {row["document_id"] for row in rows} != set(manifest["document_ids"]):
        raise ValueError("Reviewed input and selection differ")
    result = compare_sparse_models(rows, manifest["guard_folds"])
    result["label_status"] = ("synthetic_fixture" if fixture_mode
                              else "double_reviewed_development")
    result["selection_support"] = manifest["support"]
    result["custody"] = {
        "dataset_id": manifest["dataset_id"],
        "input_sha256": file_sha256(input_path),
        "selection_sha256": file_sha256(manifest_path),
        "reservation_report_sha256": manifest["reservation_report_sha256"],
        "fold_policy_version": manifest["fold_policy_version"],
        "candidate_matrix_sha256": sha256(json.dumps(
            [candidate.__dict__ for candidate in CANDIDATES], sort_keys=True
        ).encode()).hexdigest(),
    }
    return result
