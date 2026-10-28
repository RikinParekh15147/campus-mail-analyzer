"""Conservative reviewed v2 mapping to private runtime replay scenarios.

The scenarios contain source text and must remain in private memory. They are
not a sealed-test reader or a scored benchmark until reviewed input is pinned.
"""

from collections import Counter

from .contracts import ResearchDocument


def _double_reviewed(document, task):
    status = getattr(document.annotation_status, task)
    return document.gold_eligible(task) and len(set(status.reviewer_ids)) >= 2


def _message(document):
    return {
        "source_key": document.document_id,
        "subject": document.subject, "text": document.text,
        "sent_at": document.sent_at.isoformat() if document.sent_at else None,
        "thread_id": document.thread_id,
    }


def _project(document):
    """Map only explicit, resolved local entity/date/action gold."""
    expected_entities = []
    by_entity_id = {}
    identities = set()
    for entity in document.entities:
        if entity.type not in ("assignment", "event"):
            continue
        title = entity.attributes.get("title")
        if not isinstance(title, str) or not title.strip():
            return None, None, "missing_entity_title"
        match = {"title": title}
        for field in ("course", "assignment_number", "academic_term"):
            if field in entity.attributes:
                value = entity.attributes[field]
                if field == "assignment_number" and type(value) is int and value > 0:
                    value = str(value)
                if value is not None and not isinstance(value, str):
                    return None, None, "invalid_entity_identity_attribute"
                match[field] = value
        key = (entity.type, tuple(sorted(match.items())))
        if key in identities:
            return None, None, "ambiguous_entity_identity"
        identities.add(key)
        role = "assignment_deadline" if entity.type == "assignment" else "event_start"
        linked = [item for item in document.dates
                  if item.entity_id == entity.entity_id and item.role == role]
        if len(linked) > 1:
            return None, None, "ambiguous_entity_date"
        if linked and linked[0].normalized_value is None:
            return None, None, "unresolved_entity_date"
        if linked and linked[0].precision != "date":
            return None, None, "timed_entity_date_not_supported"
        date_field = "due_date" if entity.type == "assignment" else "date"
        fields = {**match, date_field: linked[0].normalized_value if linked else None}
        for field in ("status", "relevance", "participation"):
            if field in entity.attributes:
                fields[field] = entity.attributes[field]
        wanted = {
            "kind": entity.type, "anchor": document.document_id,
            "match": match, "fields": fields, "evidence": [document.document_id],
        }
        expected_entities.append(wanted)
        by_entity_id[entity.entity_id] = wanted
    expected = {"entities": expected_entities}
    if _double_reviewed(document, "actions"):
        if any(action.evidence.field != "text" for action in document.actions):
            return None, None, "subject_action_not_supported"
        expected["actions"] = [
            {"anchor": document.document_id,
             "start": action.evidence.start, "end": action.evidence.end,
             "status": action.action_status}
            for action in document.actions
        ]
        expected["action_complete_for"] = [document.document_id]
    return expected, by_entity_id, None


def _eligible(document):
    if (document.task != "academic" or document.data_origin != "designated_research"
        or document.usage_status == "quarantined"):
        return "source_policy"
    if not _double_reviewed(document, "entities") or not _double_reviewed(document, "dates"):
        return "entities_or_dates_not_double_reviewed"
    return None


def _pair(target, update, relation):
    for document in (target, update):
        reason = _eligible(document)
        if reason:
            return None, reason
    if not _double_reviewed(update, "relationships"):
        return None, "relationship_not_double_reviewed"
    if (target.dataset_id != update.dataset_id or target.relationships
        or target.context_document_ids or target.parent_document_id
        or update.context_document_ids not in ([], [target.document_id])
        or update.parent_document_id not in (None, target.document_id)):
        return None, "unsupported_update_context"
    if (target.sent_at is None or update.sent_at is None
        or update.sent_at <= target.sent_at):
        return None, "update_order_unresolved"
    if (relation.type not in ("updates", "corrects")
        or relation.target_document_id != target.document_id
        or relation.source_entity_id is None or relation.target_entity_id is None):
        return None, "unsupported_update_relation"
    original, original_by_id, reason = _project(target)
    if reason:
        return None, reason
    revised, revised_by_id, reason = _project(update)
    if reason:
        return None, reason
    before = original_by_id.get(relation.target_entity_id)
    after = revised_by_id.get(relation.source_entity_id)
    if (before is None or after is None or len(revised_by_id) != 1
        or before["kind"] != after["kind"] or before["match"] != after["match"]):
        return None, "update_entity_link_unscorable"
    date_field = "due_date" if before["kind"] == "assignment" else "date"
    if before["fields"][date_field] is None or after["fields"][date_field] is None:
        return None, "update_date_missing"
    final_entities = []
    preserve = []
    for wanted in original["entities"]:
        if wanted is before:
            final_entities.append({**wanted,
                                   "fields": {**wanted["fields"], **after["fields"]},
                                   "evidence": [target.document_id, update.document_id]})
        else:
            final_entities.append(wanted)
            preserve.append({"kind": wanted["kind"], "anchor": target.document_id,
                             "match": wanted["match"],
                             "fields": list(wanted["fields"])})
    final = {"entities": final_entities, "preserve": preserve}
    for field in ("actions", "action_complete_for"):
        if field in revised:
            final[field] = revised[field]
    return {
        "case_id": f"{target.document_id}__{update.document_id}",
        "steps": [
            {"message": _message(target), "expect": original},
            {"message": _message(update), "expect": final},
            {"replay": target.document_id, "expect": final},
        ],
    }, None


def prepare_reviewed_runtime_cases(documents):
    """Adapt single notices and uniquely linked two-notice updates; report exclusions."""
    parsed = [raw if isinstance(raw, ResearchDocument)
              else ResearchDocument.model_validate(raw) for raw in documents]
    by_id = {doc.document_id: doc for doc in parsed}
    if len(by_id) != len(parsed):
        raise ValueError("Reviewed runtime document IDs must be unique")
    incoming = Counter(relation.target_document_id for doc in parsed
                       for relation in doc.relationships)
    cases = []
    excluded = Counter()
    consumed = set()
    for document in parsed:
        if document.document_id in consumed:
            continue
        if document.relationships:
            if len(document.relationships) != 1:
                excluded["multiple_update_relations"] += 1
                continue
            relation = document.relationships[0]
            target = by_id.get(relation.target_document_id)
            if target is None:
                excluded["update_target_absent"] += 1
                continue
            if incoming[document.document_id] or target.relationships:
                excluded["unsupported_update_chain"] += 1
                continue
            if incoming[target.document_id] != 1 or target.document_id == document.document_id:
                excluded["ambiguous_update_chain"] += 1
                continue
            case, reason = _pair(target, document, relation)
            consumed.update((target.document_id, document.document_id))
            if reason:
                excluded[reason] += 1
            else:
                cases.append(case)
            continue
        if document.document_id in incoming:
            continue
        consumed.add(document.document_id)
        reason = _eligible(document)
        if reason:
            excluded[reason] += 1
            continue
        if document.context_document_ids or document.parent_document_id:
            excluded["context_or_relationship_required"] += 1
            continue
        expected, _, reason = _project(document)
        if reason:
            excluded[reason] += 1
            continue
        cases.append({"case_id": document.document_id,
                      "steps": [{"message": _message(document), "expect": expected}]})
    return {"cases": cases, "excluded": dict(excluded), "prepared": len(cases)}
