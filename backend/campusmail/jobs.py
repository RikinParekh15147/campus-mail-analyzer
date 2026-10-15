from datetime import datetime, timezone, timedelta
from .store import Conflict


class Queue:
    def __init__(self, store):
        self.store = store

    def enqueue(self, owner, task, payload, key):
        old = next(
            (x for x in self.store.list(owner, "job") if x["source_key"] == key), None
        )
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
                    and job.get("lease_until", "9999") < stamp.isoformat()
                )
                if not expired and (
                    job["status"] != "pending" or job["run_after"] > stamp.isoformat()
                ):
                    continue
                try:
                    job = self.store.patch(
                        owner,
                        job["id"],
                        {
                            "status": "running",
                            "lease_until": (stamp + timedelta(minutes=15)).isoformat(),
                        },
                        job["revision"],
                    )
                except Conflict:
                    continue
                try:
                    if job["task"] not in handlers:
                        raise ValueError("Unsupported job task")
                    handlers[job["task"]](owner, job["payload"])
                    self.store.patch(
                        owner, job["id"], {"status": "complete", "error": None}
                    )
                    count += 1
                except Exception as error:
                    attempts = job["attempts"] + 1
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
                    )
        return count
