from datetime import datetime, timezone, timedelta
from threading import Event, Thread
from .store import Conflict


class Queue:
    def __init__(self, store, lease_seconds=900, heartbeat_seconds=None):
        self.store = store
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds or lease_seconds / 3
        if self.lease_seconds <= 0 or not 0 < self.heartbeat_seconds < self.lease_seconds:
            raise ValueError("Heartbeat must be shorter than a positive lease")

    def _heartbeat(self, owner, job_id, lease, stop):
        while not stop.wait(self.heartbeat_seconds):
            now = datetime.now(timezone.utc)
            try:
                current = self.store.get(owner, job_id)
                if (
                    current["status"] != "running"
                    or current["revision"] != lease["revision"]
                    or not current.get("lease_until")
                    or current["lease_until"] <= now.isoformat()
                ):
                    lease["lost"] = True
                    return
                renewed = self.store.patch(
                    owner, job_id,
                    {"lease_until": (now + timedelta(seconds=self.lease_seconds)).isoformat()},
                    lease["revision"],
                )
                lease["revision"] = renewed["revision"]
                lease["until"] = renewed["lease_until"]
            except Exception:
                lease["lost"] = True
                return

    def enqueue(self, owner, task, payload, key, revive_complete=False):
        old = next(
            (x for x in self.store.list(owner, "job") if x["source_key"] == key), None
        )
        if old and revive_complete and old["status"] == "complete":
            return self.store.patch(owner, old["id"], {
                "status": "pending", "attempts": 0, "error": None,
                "run_after": datetime.now(timezone.utc).isoformat(),
            }, old["revision"])
        return old or self.store.put(
            owner,
            "job",
            {
                "task": task,
                "payload": payload,
                "status": "pending",
                "attempts": 0,
                "run_after": datetime.now(timezone.utc).isoformat(),
            },
            key,
        )

    def run_once(self, handlers):
        count = 0
        stamp = datetime.now(timezone.utc)
        for user in self.store.users():
            owner = user["id"]
            for job in self.store.list(owner, "job"):
                expired = (
                    job["status"] == "running"
                    and (not job.get("lease_until")
                         or job["lease_until"] < stamp.isoformat())
                )
                if not expired and (
                    job["status"] != "pending" or job["run_after"] > stamp.isoformat()
                ):
                    continue
                try:
                    claimed_at = datetime.now(timezone.utc)
                    job = self.store.patch(
                        owner,
                        job["id"],
                        {
                            "status": "running",
                            "lease_until": (claimed_at + timedelta(seconds=self.lease_seconds)).isoformat(),
                        },
                        job["revision"],
                    )
                except Conflict:
                    continue
                lease = {
                    "revision": job["revision"],
                    "until": job["lease_until"],
                    "lost": False,
                }
                stop = Event()
                heartbeat = Thread(
                    target=self._heartbeat, args=(owner, job["id"], lease, stop),
                    daemon=True,
                )
                heartbeat.start()
                error = None
                try:
                    if job["task"] not in handlers:
                        raise ValueError("Unsupported job task")
                    handlers[job["task"]](owner, job["payload"])
                except Exception as failure:
                    error = failure
                finally:
                    stop.set()
                    heartbeat.join()
                if lease["lost"] or lease["until"] <= datetime.now(timezone.utc).isoformat():
                    continue
                if error is not None:
                    attempts = job["attempts"] + 1
                    try:
                        self.store.patch(
                            owner,
                            job["id"],
                            {
                                "status": "failed" if attempts >= 3 else "pending",
                                "attempts": attempts,
                                "error": str(error)[:250],
                                "run_after": (
                                    stamp + timedelta(seconds=30 * 2**attempts)
                                ).isoformat(),
                            },
                            lease["revision"],
                        )
                    except Conflict:
                        continue
                else:
                    try:
                        self.store.patch(
                            owner, job["id"],
                            {"status": "complete", "error": None},
                            lease["revision"],
                        )
                    except Conflict:
                        continue
                    count += 1
        return count
