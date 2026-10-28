"""Explicit source boundaries for research selection.

These permissions are for this project's local experiments, not a statement
about redistribution rights. Operational profile feedback is never an input.
"""

from dataclasses import dataclass
import hashlib

SPLIT_POLICY_VERSION = "guard-hash-20pct-v1"
SPLIT_SEED = "campus-mail-data05-20261028"


def expected_split(task, guard_id):
    if task not in {"academic", "actionability"}:
        raise ValueError("Unknown prediction task")
    value = f"{SPLIT_SEED}|split|{task}|{guard_id}".encode()
    return "sealed_holdout" if int(hashlib.sha256(value).hexdigest(), 16) % 5 == 0 else "development"


@dataclass(frozen=True)
class SourceRule:
    task: str
    role: str
    family: str
    training_allowed: bool
    review_allowed: bool
    reason: str


SOURCE_RULES = {
    "scoped": SourceRule(
        "academic", "preferred_academic", "campus-mail-snapshot-20261014", True, True,
        "Designated private research; overlaps broad snapshot and has weak labels only.",
    ),
    "broad": SourceRule(
        "academic", "alternative_academic", "campus-mail-snapshot-20261014", True, True,
        "Alternative overlapping snapshot; never independent evaluation of scoped.",
    ),
    "charlie9": SourceRule(
        "actionability", "public_baseline", "enron-actionability-related-annotations", True, True,
        "Declared public sentence baseline; not campus action gold.",
    ),
    "parakweet": SourceRule(
        "actionability", "alternative_public", "enron-actionability-related-annotations", False, False,
        "Overlapping alternative annotations with unresolved conflicts; comparison only.",
    ),
    "durg-sample": SourceRule(
        "academic", "quarantined", "durg-university", False, False,
        "Usage remains quarantined; no training or reviewed benchmark selection.",
    ),
}


def require_source(source_name, task, purpose):
    """Fail closed for unknown sources and disallowed training/review inputs."""
    rule = SOURCE_RULES.get(source_name)
    if rule is None or rule.task != task:
        raise ValueError("Unknown or task-mismatched research source")
    if purpose == "train" and not rule.training_allowed:
        raise ValueError("Research source is not permitted for training")
    if purpose == "review" and not rule.review_allowed:
        raise ValueError("Research source is not permitted for review selection")
    if purpose not in {"train", "review", "inventory"}:
        raise ValueError("Unknown research source purpose")
    return rule
