"""Versioned, source-checked evidence for the legacy analysis interface."""

from dataclasses import asdict, dataclass
import json
from math import isfinite
from typing import Any


CONTRACT_VERSION = 1
ANALYSIS_SCHEMA_VERSION = 2
EXTRACTOR_VERSION = "local-analysis-v1"


@dataclass(frozen=True)
class Evidence:
    document_id: str
    field: str
    start: int
    end: int
    text: str
    locator: dict[str, Any] | None = None

    def validate(self, fields: dict[str, str]) -> None:
        if not self.document_id or self.field not in fields:
            raise ValueError("Evidence source is missing")
        source = fields[self.field]
        if (not isinstance(self.start, int) or isinstance(self.start, bool)
                or not isinstance(self.end, int) or isinstance(self.end, bool)
                or self.start < 0 or self.end <= self.start
                or self.end > len(source) or source[self.start:self.end] != self.text):
            raise ValueError("Evidence span does not match source text")
        if self.locator is not None and not isinstance(self.locator, dict):
            raise ValueError("Evidence locator must be an object")
        if self.locator is not None:
            try:
                json.dumps(self.locator, allow_nan=False)
            except (TypeError, ValueError) as error:
                raise ValueError("Evidence locator must be JSON-compatible") from error


@dataclass(frozen=True)
class FieldAssertion:
    field: str
    value: Any
    evidence: Evidence
    method: str
    method_version: str
    uncertainty: str | None = None
    calibrated_score: float | None = None

    def validate(self, fields: dict[str, str]) -> None:
        self.evidence.validate(fields)
        if not self.field or not self.method or not self.method_version:
            raise ValueError("Assertion method and field are required")
        try:
            json.dumps(self.value, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("Assertion value must be JSON-compatible") from error
        if self.uncertainty is not None and not isinstance(self.uncertainty, str):
            raise ValueError("Assertion uncertainty must be text")
        if self.calibrated_score is not None:
            if (self.method != "calibrated_model"
                    or isinstance(self.calibrated_score, bool)
                    or not isinstance(self.calibrated_score, (int, float))
                    or not isfinite(self.calibrated_score)
                    or not 0 <= self.calibrated_score <= 1):
                raise ValueError("Scores require a calibrated model and probability")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def adapt_legacy_analysis(
    document_id: str, body: str, subject: str, analysis: dict[str, Any],
    body_locators: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate legacy extraction and return its shape with typed assertions.

    The adapter does not infer offsets or probabilities. Invalid evidence stops
    processing before downstream records are updated.
    """
    fields = {"body": body, "subject": subject}
    assertions = []
    groups = {
        "dates": ("body", ("normalized", "role")),
        "subject_dates": ("subject", ("normalized", "role")),
        "date_ranges": ("body", ("start_date", "end_date")),
        "subject_date_ranges": ("subject", ("start_date", "end_date")),
        "times": ("body", ("time",)),
        "actions": ("body", ("status",)),
        "resources": ("body", ("url", "role")),
        "temporal_warnings": ("body", ("reason",)),
        "subject_temporal_warnings": ("subject", ("reason",)),
    }
    def containing_locator(start, end):
        matches = [item for item in body_locators or []
                   if type(item.get("start")) is int
                   and type(item.get("end")) is int
                   and item["start"] <= start < end <= item["end"]]
        if not matches:
            return None
        selected = min(matches, key=lambda item: (item["end"] - item["start"],
                                                  item["start"]))
        return {key: value for key, value in selected.items()}

    for group, (source_field, value_fields) in groups.items():
        for item in analysis.get(group, []):
            evidence = Evidence(
                document_id=document_id,
                field=source_field,
                start=item["start"], end=item["end"],
                text=item.get("text", item.get("url", "")),
                locator=item.get("locator") or (
                    containing_locator(item["start"], item["end"])
                    if source_field == "body" else None),
            )
            for value_field in value_fields:
                assertion = FieldAssertion(
                    field=f"{group}.{value_field}",
                    value=item.get(value_field),
                    evidence=evidence,
                    method=item.get("correction_method")
                    or item.get("method", "local_rules"),
                    method_version="personal-review-v1"
                    if item.get("correction_method") else EXTRACTOR_VERSION,
                    uncertainty=item.get("reason") if item.get("needs_review")
                    or group.endswith("warnings") else None,
                )
                assertion.validate(fields)
                assertions.append(assertion.as_dict())
    return {
        **analysis,
        "evidence_contract_version": CONTRACT_VERSION,
        "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
        "field_assertions": assertions,
    }


def source_assertion(analysis: dict[str, Any], group: str, value_field: str,
                     candidate: dict[str, Any]) -> dict[str, Any]:
    """Find the validated assertion used for a committed source field."""
    matches = [
        assertion for assertion in analysis.get("field_assertions", [])
        if assertion["field"] == f"{group}.{value_field}"
        and assertion["value"] == candidate.get(value_field)
        and assertion["evidence"]["start"] == candidate["start"]
        and assertion["evidence"]["end"] == candidate["end"]
    ]
    if len(matches) != 1:
        raise ValueError("Committed field has no unique validated assertion")
    return matches[0]


def confirmed_origin(record_id: str, value: Any) -> dict[str, Any]:
    return {"origin": "user_confirmed", "record_id": record_id, "value": value}


def span_assertion(document_id: str, body: str, field: str, value: Any,
                   start: int, end: int, method: str = "local_rules") -> dict[str, Any]:
    """Create a checked assertion for a derived field with a known body span."""
    assertion = FieldAssertion(
        field=field, value=value,
        evidence=Evidence(document_id, "body", start, end, body[start:end]),
        method=method, method_version=EXTRACTOR_VERSION,
    )
    assertion.validate({"body": body})
    return assertion.as_dict()
