import base64
from email.message import Message
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from email.utils import getaddresses
from urllib.parse import quote
from pathlib import Path
from .documents import VisibleText, text_quality, decode_bytes
from .dataset_import import (
    import_dataset as import_dataset,
    _dataset_source_key as _dataset_source_key,
)


def decode(data, charset=None):
    raw = base64.urlsafe_b64decode(data + "=" * ((-len(data)) % 4))
    return decode_bytes(raw, charset)


def part_charset(part):
    content_type = next(
        (header.get("value", "") for header in part.get("headers", [])
         if header.get("name", "").lower() == "content-type"),
        part.get("mimeType", ""),
    )
    header = Message()
    header["content-type"] = content_type
    return header.get_content_charset()


def parse_message(raw):
    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    plain = []
    markup = []
    attachments = []
    decoding_warnings = []

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
                    "charset": part_charset(part),
                }
            )
        elif body.get("data"):
            mime_type = part.get("mimeType", "").split(";", 1)[0].lower()
            if mime_type in ("text/html", "text/plain"):
                decoded, warning = decode(body["data"], part_charset(part))
                if warning:
                    decoding_warnings.append(warning)
                if mime_type == "text/html":
                    markup.append(decoded)
                else:
                    plain.append(decoded)
        for child in part.get("parts", []):
            walk(child)

    walk(payload)
    if plain:
        text = "\n".join(plain)
    else:
        parser = VisibleText()
        parser.feed("\n".join(markup))
        text = "".join(parser.parts)
    quality = text_quality(text)
    text_status = (
        "needs_text_review" if decoding_warnings or quality["status"] != "usable"
        else "usable"
    )
    received = None
    try:
        if raw.get("internalDate"):
            received = datetime.fromtimestamp(
                int(raw["internalDate"]) / 1000, timezone.utc
            )
    except (ValueError, TypeError, OverflowError):
        pass
    authored = None
    try:
        candidate = parsedate_to_datetime(headers["date"])
        if candidate.tzinfo is not None and candidate.utcoffset() is not None:
            authored = candidate
    except (KeyError, ValueError, TypeError, OverflowError):
        pass
    stamp = authored or received
    return {
        "provider_id": raw["id"],
        "thread_id": raw.get("threadId"),
        "subject": headers.get("subject", ""),
        "text": text,
        "text_quality": quality,
        "text_quality_status": text_status,
        "decoding_warnings": sorted(set(decoding_warnings)),
        "sent_at": stamp.isoformat() if stamp else None,
        "received_at": received.isoformat() if received else None,
        "relative_reference_trusted": authored is not None,
        "sender": headers.get("from", ""),
        "to": headers.get("to", ""),
        "cc": headers.get("cc", ""),
        "attachments": attachments,
        "is_self": "SENT" in raw.get("labelIds", []),
        "label_ids": raw.get("labelIds", []),
        "source_link": "https://mail.google.com/mail/u/0/#all/" + raw["id"],
    }


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
        source_key = "gmail:" + raw["id"]
        old = next(
            (m for m in self.store.list(self.owner, "message")
             if m["source_key"] == source_key),
            None,
        )
        if old and old.get("text") == parsed["text"] and old.get("subject") == parsed["subject"]:
            parsed = {**old, **parsed}
        record = self.store.put(self.owner, "message", parsed, source_key)
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
