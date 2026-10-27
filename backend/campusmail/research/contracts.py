"""Version 2 research contracts. Legacy exports require explicit migration."""

from datetime import date, datetime
import re
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from ..models import CATEGORIES

Identifier = Annotated[
    StrictStr, StringConstraints(min_length=1, max_length=256, pattern=r"^\S(?:.*\S)?$")
]
Category = Literal[*CATEGORIES]
TASKS = (
    "classification",
    "dates",
    "actions",
    "entities",
    "relationships",
    "reply_state",
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    @field_validator(
        "sent_at",
        "context_cutoff_at",
        "reference_date",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def timestamp_input(cls, value):
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError(
                "Timestamp must be an ISO string or aware datetime, not an epoch number"
            )
        return value


class AnnotationStatus(Contract):
    completeness: Literal["unannotated", "partial", "complete"] = "unannotated"
    provenance: Literal[
        "unlabeled", "source", "weak", "ai_generated", "human_reviewed", "synthetic"
    ] = "unlabeled"
    reviewer_ids: list[Identifier] = Field(default_factory=list)
    adjudication: Literal["not_required", "pending", "resolved"] = "not_required"
    adjudicator_id: Identifier | None = None

    @model_validator(mode="after")
    def consistent(self):
        if len(self.reviewer_ids) != len(set(self.reviewer_ids)):
            raise ValueError("Reviewer IDs must be unique")
        if self.completeness == "unannotated":
            if (
                self.provenance != "unlabeled"
                or self.reviewer_ids
                or self.adjudication != "not_required"
            ):
                raise ValueError("Unannotated tasks cannot claim labels or review")
        elif self.provenance == "unlabeled":
            raise ValueError("Annotated tasks require label provenance")
        if self.provenance == "human_reviewed":
            if not self.reviewer_ids:
                raise ValueError("Human review requires reviewer IDs")
        elif self.reviewer_ids or self.adjudication != "not_required":
            raise ValueError("Review metadata requires human-reviewed provenance")
        if (self.adjudication == "resolved") != (self.adjudicator_id is not None):
            raise ValueError(
                "Resolved adjudication requires an adjudicator, and only resolved adjudication accepts one"
            )
        return self


class AnnotationStatuses(Contract):
    classification: AnnotationStatus = Field(default_factory=AnnotationStatus)
    dates: AnnotationStatus = Field(default_factory=AnnotationStatus)
    actions: AnnotationStatus = Field(default_factory=AnnotationStatus)
    entities: AnnotationStatus = Field(default_factory=AnnotationStatus)
    relationships: AnnotationStatus = Field(default_factory=AnnotationStatus)
    reply_state: AnnotationStatus = Field(default_factory=AnnotationStatus)


class Locator(Contract):
    page: Annotated[StrictInt, Field(ge=1)] | None = None
    sheet: Identifier | None = None
    row: Annotated[StrictInt, Field(ge=1)] | None = None
    cell: Identifier | None = None


class Evidence(Contract):
    field: Literal["text", "subject"] = "text"
    start: Annotated[StrictInt, Field(ge=0)]
    end: Annotated[StrictInt, Field(gt=0)]
    text: Annotated[StrictStr, Field(min_length=1)]
    locator: Locator | None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("Evidence must be a nonempty half-open span")
        return self


class OffsetMapping(Contract):
    """Map canonical body text back to optional original_text."""

    start: Annotated[StrictInt, Field(ge=0)]
    end: Annotated[StrictInt, Field(gt=0)]
    original_start: Annotated[StrictInt, Field(ge=0)]
    original_end: Annotated[StrictInt, Field(gt=0)]
    transformation: Literal["exact", "normalized"] = "exact"


class DateAnnotation(Contract):
    evidence: Evidence
    role: Literal[
        "assignment_deadline",
        "registration_deadline",
        "event_start",
        "event_end",
        "exam_date",
        "publication_date",
        "other",
        "unknown",
    ]
    normalized_value: StrictStr | None = None
    precision: Literal["date", "datetime"] = "date"
    timezone: StrictStr | None = None
    reference_date: AwareDatetime | None = None
    entity_id: Identifier | None = None
    needs_review: StrictBool = False
    reason: StrictStr | None = None

    @field_validator("timezone")
    @classmethod
    def zone_valid(cls, value):
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("Unknown timezone") from None
        return value

    @model_validator(mode="after")
    def value_valid(self):
        if self.normalized_value is not None:
            if self.precision == "date":
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.normalized_value):
                    raise ValueError("Date precision requires an ISO calendar date")
                date.fromisoformat(self.normalized_value)
            else:
                parsed = datetime.fromisoformat(
                    self.normalized_value.replace("Z", "+00:00")
                )
                if "T" not in self.normalized_value or parsed.tzinfo is None:
                    raise ValueError("Datetime precision requires an explicit offset")
                if (
                    self.timezone
                    and parsed.astimezone(ZoneInfo(self.timezone)).utcoffset()
                    != parsed.utcoffset()
                ):
                    raise ValueError("Timezone and datetime offset disagree")
        if (
            self.normalized_value is None or self.role == "unknown"
        ) and not self.needs_review:
            raise ValueError("Unresolved dates require review")
        if self.needs_review and not (self.reason and self.reason.strip()):
            raise ValueError("Review requires a reason")
        return self


class ActionAnnotation(Contract):
    evidence: Evidence
    actor: Literal["student", "sender", "recipient", "broadcast", "other", "unknown"]
    action_type: Literal[
        "submit",
        "register",
        "attend",
        "reply",
        "upload",
        "apply",
        "read",
        "pay",
        "bring",
        "complete",
        "other",
        "unknown",
    ]
    action_status: Literal["required", "optional", "completed", "negated", "uncertain"]
    entity_id: Identifier | None = None
    needs_review: StrictBool = False


class EntityAnnotation(Contract):
    entity_id: Identifier
    type: Literal[
        "course", "assignment", "event", "meeting", "assessment_result", "resource"
    ]
    evidence_spans: list[Evidence] = Field(min_length=1)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)


class RelationshipAnnotation(Contract):
    relationship_id: Identifier
    target_document_id: Identifier
    source_entity_id: Identifier | None = None
    target_entity_id: Identifier | None = None
    type: Literal[
        "supports",
        "same_event",
        "same_assignment",
        "updates",
        "cancels",
        "corrects",
        "exact_duplicate",
        "candidate_supersedes",
    ]
    evidence_spans: list[Evidence] = Field(min_length=1)
    needs_review: StrictBool = False


class GroupingRelation(Contract):
    """A source-declared grouping edge, not a reviewed semantic annotation."""

    relationship_id: Identifier
    target_document_id: Identifier
    type: Identifier


class ResearchDocument(Contract):
    schema_version: Literal["2.0"]
    dataset_id: Identifier
    document_id: Identifier
    task: Literal["academic", "actionability"]
    data_origin: Literal["designated_research", "public", "synthetic"]
    source_type: Identifier
    usage_status: Literal["unverified", "permitted", "quarantined"] = "unverified"
    source_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    subject: Annotated[StrictStr, Field(max_length=10_000)] = ""
    text: Annotated[StrictStr, Field(max_length=2_000_000)]
    text_status: Literal["available", "unavailable"] = "available"
    original_text: Annotated[StrictStr, Field(max_length=2_000_000)] | None = None
    offset_map: list[OffsetMapping] = Field(default_factory=list)
    sent_at: AwareDatetime | None = None
    timezone: StrictStr | None = None
    context_cutoff_at: AwareDatetime | None = None
    context_document_ids: list[Identifier] = Field(default_factory=list)
    thread_id: Identifier | None = None
    parent_document_id: Identifier | None = None
    duplicate_group_id: Identifier | None = None
    template_group_id: Identifier | None = None
    leakage_group_id: Identifier | None = None
    update_family_id: Identifier | None = None
    grouping_relations: list[GroupingRelation] = Field(default_factory=list)
    primary_category: Category | None = None
    secondary_categories: list[Category] = Field(default_factory=list)
    secondary_categories_complete: StrictBool = False
    actionability_label: StrictBool | None = None
    annotation_status: AnnotationStatuses = Field(default_factory=AnnotationStatuses)
    dates: list[DateAnnotation] = Field(default_factory=list)
    actions: list[ActionAnnotation] = Field(default_factory=list)
    entities: list[EntityAnnotation] = Field(default_factory=list)
    relationships: list[RelationshipAnnotation] = Field(default_factory=list)
    reply_state: (
        Literal[
            "needs_reply",
            "waiting_for_other",
            "resolved",
            "uncertain",
            "not_applicable",
        ]
        | None
    ) = None

    @field_validator("timezone")
    @classmethod
    def zone_valid(cls, value):
        return DateAnnotation.zone_valid(value)

    def gold_eligible(self, task):
        if task not in TASKS:
            raise ValueError("Unknown annotation task")
        status = getattr(self.annotation_status, task)
        return (
            status.completeness == "complete"
            and status.provenance == "human_reviewed"
            and status.adjudication != "pending"
        )

    @model_validator(mode="after")
    def consistent(self):
        if self.text_status == "available" and not self.text.strip():
            raise ValueError("Canonical text must not be blank")
        if self.text_status == "unavailable":
            if self.text.strip():
                raise ValueError("Unavailable text cannot contain canonical content")
            if any(
                getattr(self.annotation_status, task).completeness != "unannotated"
                for task in TASKS
            ):
                raise ValueError(
                    "Unavailable text is context-only, not labeled ML input"
                )
        if (
            self.sent_at
            and self.context_cutoff_at
            and self.sent_at > self.context_cutoff_at
        ):
            raise ValueError("Document timestamp exceeds observation cutoff")
        if self.context_document_ids and self.context_cutoff_at is None:
            raise ValueError("Context references require an observation cutoff")
        if (
            self.parent_document_id == self.document_id
            or self.document_id in self.context_document_ids
        ):
            raise ValueError(
                "Parent/context references cannot refer to the same document"
            )
        if len(set(self.context_document_ids)) != len(self.context_document_ids):
            raise ValueError("Context references must be unique")
        if (
            len(set(self.secondary_categories)) != len(self.secondary_categories)
            or self.primary_category in self.secondary_categories
        ):
            raise ValueError("Category labels must be unique")
        if self.task == "academic":
            if self.actionability_label is not None:
                raise ValueError(
                    "Academic task cannot use a binary actionability label"
                )
            label = self.primary_category
        else:
            if (
                self.primary_category
                or self.secondary_categories
                or self.secondary_categories_complete
            ):
                raise ValueError(
                    "Actionability task cannot use academic category labels"
                )
            label = self.actionability_label
        status = self.annotation_status.classification
        if status.completeness == "unannotated" and (
            label is not None
            or self.secondary_categories
            or self.secondary_categories_complete
        ):
            raise ValueError("Labels require declared annotation provenance")
        if status.completeness == "complete" and label is None:
            raise ValueError("Complete classification requires a label")
        for task in TASKS[1:]:
            value = getattr(self, task)
            if (
                value
                and getattr(self.annotation_status, task).completeness == "unannotated"
            ):
                raise ValueError("Annotations require declared task provenance")
        if (
            self.annotation_status.reply_state.completeness == "complete"
            and self.reply_state is None
        ):
            raise ValueError("Complete reply-state annotation requires a state")
        if self.reply_state is not None and self.context_cutoff_at is None:
            raise ValueError("Reply-state annotation requires an observation cutoff")
        entities = {item.entity_id for item in self.entities}
        if len(entities) != len(self.entities):
            raise ValueError("Entity IDs must be unique within a document")
        if len({r.relationship_id for r in self.relationships}) != len(
            self.relationships
        ):
            raise ValueError("Relationship IDs must be unique within a document")
        if len({r.relationship_id for r in self.grouping_relations}) != len(
            self.grouping_relations
        ):
            raise ValueError(
                "Grouping relationship IDs must be unique within a document"
            )
        evidence = [item.evidence for item in self.dates + self.actions]
        for item in self.entities + self.relationships:
            evidence.extend(item.evidence_spans)
        for span in evidence:
            source = getattr(self, span.field)
            if span.end > len(source) or source[span.start : span.end] != span.text:
                raise ValueError("Evidence must exactly match canonical source offsets")
        local_refs = [item.entity_id for item in self.dates + self.actions]
        local_refs.extend(r.source_entity_id for r in self.relationships)
        if any(ref is not None and ref not in entities for ref in local_refs):
            raise ValueError("Local entity reference does not exist")
        for mapping in self.offset_map:
            if (
                self.original_text is None
                or not 0 <= mapping.start < mapping.end <= len(self.text)
                or not 0
                <= mapping.original_start
                < mapping.original_end
                <= len(self.original_text)
            ):
                raise ValueError("Offset mapping is outside source bounds")
            if (
                mapping.transformation == "exact"
                and self.text[mapping.start : mapping.end]
                != self.original_text[mapping.original_start : mapping.original_end]
            ):
                raise ValueError("Exact offset mapping must preserve text")
        return self
