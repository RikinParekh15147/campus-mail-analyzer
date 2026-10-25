import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from email.utils import getaddresses
from urllib.parse import quote
import hashlib
import json
import re
from pathlib import Path
from .documents import VisibleText
from .models import CATEGORIES


def decode(data):
    return base64.urlsafe_b64decode(data + "=" * ((-len(data)) % 4)).decode(
        "utf-8", errors="replace"
    )


def parse_message(raw):
    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    plain = []
    markup = []
    attachments = []

    def walk(part):
        body = part.get("body", {})
        if part.get("filename"):
            attachments.append(
                {
                    "filename": Path(part["filename"]).name,
                    "provider_id": body.get("attachmentId"),
                    "inline_data": body.get("data"),
                    "mime_type": part.get("mimeType"),
                    "size": body.get("size"),
                }
            )
        elif body.get("data"):
            if part.get("mimeType") == "text/html":
                markup.append(decode(body["data"]))
            elif part.get("mimeType") == "text/plain":
                plain.append(decode(body["data"]))
        for child in part.get("parts", []):
            walk(child)

    walk(payload)
    if plain:
        text = "\n".join(plain)
    else:
        parser = VisibleText()
        parser.feed("\n".join(markup))
        text = "".join(parser.parts)
    stamp = None
    try:
        stamp = (
            datetime.fromtimestamp(
                int(raw["internalDate"]) / 1000, timezone.utc
            ).isoformat()
            if raw.get("internalDate")
            else parsedate_to_datetime(headers["date"]).isoformat()
        )
    except (KeyError, ValueError, TypeError):
        pass
    return {
        "provider_id": raw["id"],
        "thread_id": raw.get("threadId"),
        "subject": headers.get("subject", ""),
        "text": text,
        "sent_at": stamp,
        "sender": headers.get("from", ""),
        "to": headers.get("to", ""),
        "cc": headers.get("cc", ""),
        "attachments": attachments,
        "is_self": "SENT" in raw.get("labelIds", []),
        "label_ids": raw.get("labelIds", []),
        "source_link": "https://mail.google.com/mail/u/0/#all/" + raw["id"],
    }


def _dataset_source_key(dataset_id, document_id):
    """A path-independent, unambiguous key for an operational import."""
    if not isinstance(dataset_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", dataset_id
    ):
        raise ValueError("A stable dataset_id is required for import")
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("Every imported record needs a document_id")
    identity = json.dumps([dataset_id, document_id], ensure_ascii=False)
    return "dataset:v2:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def import_dataset(store, owner, path, on_message=None, limit=None, *, dataset_id):
    path = Path(path)
    _dataset_source_key(dataset_id, "preflight")
    if limit is not None and (not isinstance(limit, int) or limit < 1):
        raise ValueError("Import limit must be a positive integer")
    count = 0
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"Import row {line_number} must be an object")
            if row.get("schema_version") == "2.0":
                raise ValueError("Research v2 export is not an operational import")
            if row.get("dataset_id", dataset_id) != dataset_id:
                raise ValueError(f"Import row {line_number} has a different dataset_id")
            if not isinstance(row.get("text"), str) or not row["text"].strip():
                continue
            source_key = _dataset_source_key(dataset_id, row.get("document_id"))
            category = row.get("primary_category")
            metadata = row.get("source_metadata") or {}
            payload = {
                "text": row["text"],
                "subject": row.get("subject", ""),
                "sent_at": row.get("sent_at"),
                "thread_id": row.get("thread_id"),
                "source_category": category if category in CATEGORIES else None,
                "label_provenance": row.get("label_provenance", "unknown"),
                "source_type": row.get("source_type"),
                "sanitized": True,
                "dataset_id": dataset_id,
                "source_metadata": metadata,
                "imported_resources": row.get("resources", []),
                "parent_message_id": row.get("parent_message_id"),
                "original_document_id": row.get("document_id"),
                "original_message_id": row.get("message_id"),
                "is_self": metadata.get("sender_is_account", False),
            }
            for field in (
                "parent_document_id",
                "duplicate_group_id",
                "template_group_id",
                "leakage_group_id",
                "update_family_id",
            ):
                if field in row:
                    payload[field] = row[field]
            record = store.put(owner, "message", payload, source_key)
            if on_message:
                on_message(owner, record)
            count += 1
            if limit is not None and count >= limit:
                break
    return count


class GmailSync:
    def __init__(self, store, owner, api, on_message=None, scope=None):
        self.store, self.owner, self.api, self.on_message = (
            store,
            owner,
            api,
            on_message,
        )
        self.scope = scope or {"labels": ["INBOX"]}

    def ingest(self, raw, context=False):
        parsed = parse_message(raw)
        account = getattr(self, "account_email", None)
        if account:
            recipients = {
                email.lower() for _, email in getaddresses([parsed.get("to", "")])
            }
            carbon = {
                email.lower() for _, email in getaddresses([parsed.get("cc", "")])
            }
            parsed["cc_only"] = (
                account.lower() in carbon and account.lower() not in recipients
            )
            parsed["source_link"] = (
                "https://mail.google.com/mail/?authuser="
                + quote(account, safe="")
                + "#all/"
                + raw["id"]
            )
        if not context:
            if self.scope.get("labels") and not set(self.scope["labels"]) & set(
                parsed["label_ids"]
            ):
                return
            if self.scope.get("senders") and not any(
                s.lower() in parsed["sender"].lower() for s in self.scope["senders"]
            ):
                return
        record = self.store.put(self.owner, "message", parsed, "gmail:" + raw["id"])
        if self.on_message:
            self.on_message(self.owner, record)

    def run(self, limit=50):
        state = next(iter(self.store.list(self.owner, "sync_state")), None)
        profile = self.api.get("profile")
        checkpoint = profile["historyId"]
        self.account_email = profile.get("emailAddress")
        ids = set()
        warnings = []

        def history(start):
            token = None
            latest = start
            while True:
                data = self.api.get(
                    "history",
                    params={
                        "startHistoryId": start,
                        **({"pageToken": token} if token else {}),
                    },
                )
                latest = data.get("historyId", latest)
                for item in data.get("history", []):
                    for msg in item.get("messagesAdded", []):
                        ids.add(msg["message"]["id"])
                token = data.get("nextPageToken")
                if not token:
                    return latest

        bootstrap = state is None
        if state:
            try:
                checkpoint = history(state["history_id"])
            except LookupError:
                bootstrap = True
                warnings.append("History expired; recent scope reconciled")
        if bootstrap:
            token = None
            while len(ids) < limit:
                data = self.api.get(
                    "messages",
                    params={
                        "maxResults": min(50, limit - len(ids)),
                        "labelIds": self.scope.get("labels", ["INBOX"]),
                        **({"pageToken": token} if token else {}),
                    },
                )
                ids.update(m["id"] for m in data.get("messages", []))
                token = data.get("nextPageToken")
                if not token:
                    break
            try:
                checkpoint = history(checkpoint)
            except LookupError:
                warnings.append(
                    "Bootstrap history unavailable; next run will reconcile again"
                )
        threads = set()
        for mid in sorted(ids):
            raw = self.api.get("messages/" + mid, params={"format": "full"})
            self.ingest(raw)
            tid = raw.get("threadId")
            if tid and tid not in threads:
                threads.add(tid)
                for message in self.api.get(
                    "threads/" + tid, params={"format": "full"}
                ).get("messages", []):
                    self.ingest(message, context=True)
        self.store.put(
            self.owner,
            "sync_state",
            {
                "history_id": checkpoint,
                "last_sync": datetime.now(timezone.utc).isoformat(),
                "warnings": warnings,
                "scope": self.scope,
            },
            "gmail",
        )
        return {"messages": len(ids), "warnings": warnings}

    def search_context(self, query, limit=10):
        if not 1 <= limit <= 20:
            raise ValueError("Context search is limited to 20 messages")
        data = self.api.get(
            "messages",
            params={
                "q": query,
                "maxResults": limit,
                "labelIds": self.scope.get("labels", []),
            },
        )
        for item in data.get("messages", [])[:limit]:
            self.ingest(
                self.api.get("messages/" + item["id"], params={"format": "full"})
            )
        return {"messages": len(data.get("messages", [])[:limit])}
