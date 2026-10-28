import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
import hmac
import json
import os
from pathlib import Path
import secrets
from typing import Any, Literal
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Depends, Header, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from .application import Application, PROJECT
from .store import NotFound, Conflict
from .calendar import Timetable, Holidays, instant
from .google import GoogleConnection


class ProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class NoticeInput(BaseModel):
    text: str = Field(min_length=1, max_length=2_000_000)
    subject: str = Field(default="", max_length=500)
    reference_date: str | None = None


class FeedbackInput(BaseModel):
    record_id: str
    field: str
    value: Any
    expected_revision: int | None = None


class ImportInput(BaseModel):
    collection: Literal["scoped", "broad"] = "scoped"
    limit: int | None = Field(default=None, ge=1, le=10000)


class SettingsInput(BaseModel):
    timezone: str = "Asia/Kolkata"
    sync_minutes: int = Field(default=10, ge=5, le=1440)
    gmail_labels: list[str] = ["INBOX"]
    senders: list[str] = []
    calendar_ids: list[str] = ["primary"]


def create_app(data_dir=None, bootstrap_key=None, worker=False, project_root=None):
    services = Application(
        data_dir or Path(os.environ.get("CAMPUS_DATA_DIR", PROJECT / "runtime")),
        project_root,
    )
    bootstrap_key = (
        bootstrap_key
        or os.environ.get("CAMPUS_BOOTSTRAP_KEY")
        or secrets.token_urlsafe(32)
    )

    @asynccontextmanager
    async def lifespan(app):
        async def loop():
            while True:
                try:
                    await asyncio.to_thread(services.tick)
                except Exception:
                    import logging

                    logging.getLogger("campusmail").exception("Background tick failed")
                await asyncio.sleep(10)

        task = asyncio.create_task(loop()) if worker else None
        yield
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="Campus Mail Analyser", version="0.1.0", lifespan=lifespan)
    app.state.services = services

    def bootstrap(x_bootstrap_key: str = Header(default="")):
        if not hmac.compare_digest(x_bootstrap_key, bootstrap_key):
            raise HTTPException(401, "Desktop authorization required")

    def owner(authorization: str = Header(default="")):
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Sign in to a profile")
        try:
            return services.store.owner_for_session(authorization[7:])
        except NotFound:
            raise HTTPException(401, "Session expired")

    @app.exception_handler(NotFound)
    async def missing(request, error):
        return JSONResponse({"detail": str(error)}, 404)

    @app.exception_handler(Conflict)
    async def conflict(request, error):
        return JSONResponse({"detail": str(error)}, 409)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, 422)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/profiles", dependencies=[Depends(bootstrap)])
    def profiles():
        return services.store.users()

    @app.post("/profiles", dependencies=[Depends(bootstrap)])
    def new_profile(body: ProfileInput):
        user = services.store.create_user(body.name)
        return {**user, "token": services.store.session(user["id"])}

    @app.post("/profiles/{profile_id}/session", dependencies=[Depends(bootstrap)])
    def select_profile(profile_id: str):
        if not any(u["id"] == profile_id for u in services.store.users()):
            raise NotFound("Profile not found")
        return {"token": services.store.session(profile_id)}

    @app.get("/dashboard")
    def dashboard(account=Depends(owner)):
        return services.dashboard(account)

    @app.get("/records/{kind}")
    def records(kind: str, account=Depends(owner)):
        if kind not in {
            "assignment",
            "event",
            "resource",
            "message",
            "review",
            "profile_fact",
            "course",
            "grade",
            "reply_request",
            "feedback",
            "preference",
            "notification",
            "job",
            "proposal",
            "timetable",
            "holidays",
            "calendar_item",
            "briefing",
            "external_event",
        }:
            raise ValueError("Unsupported record collection")
        data = services.store.list(account, kind)
        if kind == "job":
            data = [{k: v for k, v in r.items() if k != "payload"} for r in data]
        return data

    @app.get("/records/{record_id}/detail")
    def detail(record_id: str, account=Depends(owner)):
        return services.store.get(account, record_id)

    @app.post("/ingest")
    def ingest(body: NoticeInput, account=Depends(owner)):
        return services.ingest(account, body.text, body.subject, body.reference_date)

    @app.post("/dataset/import")
    def import_data(body: ImportInput, account=Depends(owner)):
        services.dataset_path(body.collection)
        return services.queue.enqueue(
            account,
            "import",
            body.model_dump(),
            "import:" + body.collection + ":" + str(body.limit),
        )

    @app.post("/attachments")
    async def attachment(
        file: UploadFile = File(), parent_id: str | None = None, account=Depends(owner)
    ):
        if parent_id:
            services.store.get(account, parent_id)
        return await asyncio.to_thread(
            services.attach,
            account,
            await file.read(20 * 1024 * 1024 + 1),
            file.filename or "attachment",
            parent_id,
        )

    @app.get("/resources/{record_id}/download")
    def download(record_id: str, account=Depends(owner)):
        resource = services.store.get(account, record_id)
        if resource["kind"] != "resource" or not resource.get("path"):
            raise NotFound("Original file unavailable in this import")
        path = Path(resource["path"]).resolve()
        root = (services.data_dir / "blobs" / account).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise NotFound("Resource file unavailable")
        return FileResponse(
            path, filename=Path(resource.get("filename", "resource")).name
        )

    @app.post("/feedback")
    def feedback(body: FeedbackInput, account=Depends(owner)):
        result = services.personal.feedback(
            account, body.record_id, body.field, body.value, body.expected_revision
        )
        if result["kind"] == "profile_fact":
            services.queue.enqueue(
                account,
                "reprocess",
                {},
                "profile:" + result["id"] + ":" + str(result["revision"]),
            )
        return result

    @app.post("/reviews/{record_id}/answer")
    def answer(record_id: str, body: dict, account=Depends(owner)):
        question = services.store.get(account, record_id)
        result = services.personal.answer(
            account, record_id, body.get("value"), body.get("defer", False)
        )
        if not body.get("defer") and question.get("record_id"):
            record = services.store.get(account, question["record_id"])
            if record["kind"] == "message":
                services.process(account, record)
            elif record["kind"] == "profile_fact":
                services.queue.enqueue(
                    account,
                    "reprocess",
                    {},
                    "answer:" + question["id"] + ":" + str(result["revision"]),
                )
            elif (
                question.get("field") == "relevance"
                and body.get("value") == "applicable"
                and record.get("course")
            ):
                services.engine.fact(
                    account,
                    "enrollment:" + record["course"],
                    True,
                    "review:" + question["id"],
                    True,
                )
                services.queue.enqueue(
                    account, "reprocess", {}, "enrollment:" + question["id"]
                )
        return result

    @app.post("/profile/facts")
    def profile_fact(body: dict, account=Depends(owner)):
        field = body.get("field", "")
        value = body.get("value")
        if field not in (
            "roll_number",
            "university",
            "program",
            "semester",
            "batch",
            "section",
            "lab_group",
            "field",
            "enrollment_complete",
        ) and not field.startswith("enrollment:"):
            raise ValueError("Unsupported academic profile field")
        if value is None or value == "":
            raise ValueError("A confirmed value is required")
        result = services.engine.fact(account, field, value, "user-confirmation", True)
        services.store.put(
            account,
            "feedback",
            {
                "record_id": result["id"],
                "field": field,
                "value": value,
                "scope": "personal_only",
                "weight": 2,
            },
        )
        services.queue.enqueue(
            account,
            "reprocess",
            {},
            "profile:" + result["id"] + ":" + str(result["revision"]),
        )
        return result

    @app.post("/preferences/reset")
    def reset(account=Depends(owner)):
        services.personal.reset(account)
        return {"reset": True}

    @app.get("/calendar")
    def entries(start: date, end: date, account=Depends(owner)):
        return services.calendar.entries(account, start, end)

    @app.get("/conflicts")
    def conflicts(start: date, end: date, account=Depends(owner)):
        return services.calendar.conflicts(account, start, end)

    @app.post("/calendar/items")
    def personal_item(body: dict, account=Depends(owner)):
        if not body.get("title"):
            raise ValueError("Title is required")
        zone = ZoneInfo(services.settings(account).get("timezone", "Asia/Kolkata"))

        def local_time(value):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                left = parsed.replace(tzinfo=zone, fold=0)
                right = parsed.replace(tzinfo=zone, fold=1)
                if (
                    left.utcoffset() != right.utcoffset()
                    or left.astimezone(timezone.utc)
                    .astimezone(zone)
                    .replace(tzinfo=None)
                    != parsed
                ):
                    raise ValueError(
                        "Ambiguous local time; supply an explicit UTC offset"
                    )
                parsed = left
            return parsed

        left, right = local_time(body["start"]), local_time(body["end"])
        if right <= left:
            raise ValueError("End must follow start")
        return services.store.put(
            account,
            "calendar_item",
            {
                "title": str(body["title"])[:300],
                "start": left.isoformat(),
                "end": right.isoformat(),
                "flexible": bool(body.get("flexible", True)),
            },
        )

    @app.post("/conflicts/{record_id}/propose")
    def propose(record_id: str, account=Depends(owner)):
        return services.calendar.propose(account, record_id)

    @app.post("/proposals/{record_id}/approve")
    def approve(record_id: str, account=Depends(owner)):
        return services.calendar.approve(account, record_id)

    @app.post("/imports/{kind}")
    def schedule_import(
        kind: Literal["timetable", "holidays"], body: dict, account=Depends(owner)
    ):
        fn = (
            services.calendar.import_timetable
            if kind == "timetable"
            else services.calendar.import_holidays
        )
        parsed = fn(account, body.get("data", {}), bool(body.get("confirm")))
        if kind == "timetable" and body.get("confirm"):
            for field, value in parsed["student_context"].items():
                services.engine.fact(account, field, value, "confirmed-timetable", True)
            for session in parsed["sessions"]:
                services.engine.fact(
                    account,
                    "enrollment:" + session["course"],
                    True,
                    "confirmed-timetable",
                    True,
                )
            services.engine.fact(
                account, "enrollment_complete", True, "confirmed-timetable", True
            )
            services.queue.enqueue(
                account, "reprocess", {}, "timetable:" + secrets.token_hex(8)
            )
        return parsed

    @app.get("/prompts/{kind}")
    def prompt(kind: Literal["timetable", "holidays"], account=Depends(owner)):
        schema = (Timetable if kind == "timetable" else Holidays).model_json_schema()
        text = (
            "Interpret my personal timetable. Before final JSON, ask which program, semester, batch, section, lab group and electives apply. A schedule may combine three or more batches: do not combine their sessions. Ask about unclear entries, rotating weeks, AM/PM, dates, timezone and overlaps. Show the interpreted week for confirmation."
            if kind == "timetable"
            else "Interpret my holiday list. Clarify academic year, campus/batch applicability, date ranges and whether classes are suspended. Do not assume independently scheduled exams or events are cancelled. Show the interpreted list for confirmation."
        )
        text += (
            " Ask every necessary clarification; do not guess. After resolving ambiguity, output only JSON matching this schema, without Markdown fences.\n"
            + json.dumps(schema, indent=2)
        )
        return {"prompt": text, "schema": schema}

    @app.get("/summary")
    def summary(days: int = Query(default=7, ge=1, le=30), account=Depends(owner)):
        return services.briefings.generate(account, days=days)

    @app.post("/summary/provider")
    def configure_summary(body: dict, account=Depends(owner)):
        import keyring
        from .summary_api import APIEnhancer

        APIEnhancer(
            body.get("endpoint", ""), body.get("model", ""), body.get("api_key", "")
        )
        try:
            keyring.set_password("campusmail", account + ":summary", body["api_key"])
        except Exception:
            raise ValueError("OS credential vault unavailable; API key was not saved")
        return services.store.put(
            account,
            "summary_provider",
            {"endpoint": body["endpoint"], "model": body["model"]},
            "provider",
        )

    @app.post("/summary/enhance")
    def enhanced_summary(account=Depends(owner)):
        import keyring
        from .summary_api import APIEnhancer
        from .briefings import Briefings

        provider = next(iter(services.store.list(account, "summary_provider")), None)
        if not provider:
            raise ValueError("Configure an optional summary provider in Settings first")
        local = services.briefings.generate(account)
        cache = next(
            (
                r
                for r in services.store.list(account, "summary_cache")
                if r["source_key"]
                == local["fingerprint"] + ":" + str(provider["revision"])
            ),
            None,
        )
        if cache:
            return cache["report"]
        try:
            key = keyring.get_password("campusmail", account + ":summary")
        except Exception:
            key = None
        if not key:
            raise ValueError("Summary API credential unavailable")
        result = services.briefings.generate(
            account, enhancer=APIEnhancer(provider["endpoint"], provider["model"], key)
        )
        if result["method"] == "api_assisted":
            services.store.put(
                account,
                "summary_cache",
                {"report": result},
                local["fingerprint"] + ":" + str(provider["revision"]),
            )
        return result

    @app.post("/notifications/read")
    def read_notifications(account=Depends(owner)):
        for notification in services.store.list(account, "notification"):
            if not notification.get("read"):
                services.store.patch(account, notification["id"], {"read": True})
        return {"read": True}

    @app.post("/marks/extract")
    def extract_marks(body: dict, account=Depends(owner)):
        for field in ("course", "assessment", "text"):
            if not body.get(field):
                raise ValueError(field + " is required")
        source = services.store.put(
            account,
            "message",
            {
                "subject": body["course"] + " " + body["assessment"] + " results",
                "text": body["text"],
            },
        )
        return services.grades.extract(
            account, body["text"], body["course"], body["assessment"], source["id"]
        )

    @app.get("/settings")
    def settings(account=Depends(owner)):
        return services.settings(account)

    @app.put("/settings")
    def settings_update(body: SettingsInput, account=Depends(owner)):
        ZoneInfo(body.timezone)
        return services.store.put(account, "settings", body.model_dump(), "settings")

    @app.get("/connections")
    def connections(account=Depends(owner)):
        return {s: GoogleConnection(account, s).status() for s in ("gmail", "calendar")}

    @app.post("/connections/{service}/connect")
    def connect(
        service: Literal["gmail", "calendar"], body: dict, account=Depends(owner)
    ):
        if "installed" not in body:
            raise ValueError("Select a Google Desktop OAuth client JSON file")
        services.oauth_configs[(account, service)] = body
        return services.queue.enqueue(
            account,
            "connect",
            {"service": service},
            "connect:" + service + ":" + secrets.token_hex(8),
        )

    @app.post("/connections/{service}/sync")
    def sync(service: Literal["gmail", "calendar"], account=Depends(owner)):
        return services.queue.enqueue(
            account, service + "_sync", {}, service + ":manual:" + secrets.token_hex(8)
        )

    @app.delete("/connections/{service}")
    def disconnect(service: Literal["gmail", "calendar"], account=Depends(owner)):
        GoogleConnection(account, service).disconnect()
        return {"connected": False}

    @app.get("/models")
    def models(account=Depends(owner)):
        from .model_registry import model_health, resolve_runtime_model

        reports = {}
        for task in ("academic", "actionability"):
            task_dir = services.project / "artifacts/models" / task
            health = model_health(task_dir, task=task)
            if health["status"] == "verified":
                try:
                    path, _ = resolve_runtime_model(task_dir, task=task)
                    metrics = json.loads((path.parent / "metrics.json").read_text())
                    if not isinstance(metrics, dict):
                        raise ValueError("Model metrics must be an object")
                    reports[task] = {**metrics, "health": health}
                except (OSError, ValueError):
                    reports[task] = {"health": {"status": "rules_only",
                                                 "reason": "Model metrics are unreadable"}}
            else:
                reports[task] = {"health": health}
        return reports

    @app.get("/updates")
    def updates(account=Depends(owner)):
        # Cheap version polling avoids an always-open connection in the desktop renderer.
        records = services.store.list(account)
        return {
            "version": max((r["updated_at"] for r in records), default=""),
            "jobs_running": sum(
                r["kind"] == "job" and r["status"] in ("pending", "running")
                for r in records
            ),
        }

    return app
