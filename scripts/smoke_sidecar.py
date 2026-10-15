"""Run the frozen sidecar against a fresh temporary profile (no external services)."""

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import secrets
import socket
import subprocess
import time
import requests


def main():
    root = Path(__file__).resolve().parents[1]
    executable = (
        root
        / "dist/campusmail-backend"
        / ("campusmail-backend.exe" if os.name == "nt" else "campusmail-backend")
    )
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    secret = secrets.token_urlsafe(24)
    with TemporaryDirectory(prefix="campus-frozen-") as directory:
        log = Path(directory) / "server.log"
        with log.open("w") as output:
            process = subprocess.Popen(
                [
                    str(executable),
                    "serve",
                    "--port",
                    str(port),
                    "--data-dir",
                    directory,
                ],
                env={**os.environ, "CAMPUS_BOOTSTRAP_KEY": secret},
                stdout=output,
                stderr=output,
            )
            base = f"http://127.0.0.1:{port}"
            try:
                for _ in range(180):
                    try:
                        if requests.get(base + "/health", timeout=1).ok:
                            break
                    except requests.RequestException:
                        pass
                    if process.poll() is not None:
                        raise RuntimeError(log.read_text()[-3000:])
                    time.sleep(0.25)
                else:
                    raise RuntimeError(
                        "Frozen sidecar did not become ready: "
                        + log.read_text()[-3000:]
                    )
                profile = requests.post(
                    base + "/profiles",
                    headers={"X-Bootstrap-Key": secret},
                    json={"name": "Frozen smoke test"},
                    timeout=10,
                )
                profile.raise_for_status()
                headers = {"Authorization": "Bearer " + profile.json()["token"]}
                notice = requests.post(
                    base + "/ingest",
                    headers=headers,
                    json={
                        "subject": "NLP201 Assignment 2",
                        "text": "NLP201 Assignment 2 must submit by 25 October 2026 at 5:00 PM.",
                    },
                    timeout=60,
                )
                if not notice.ok:
                    raise RuntimeError(
                        f"Frozen ingestion failed ({notice.status_code}): "
                        + notice.text
                        + "\n"
                        + log.read_text()[-8000:]
                    )
                assert (
                    notice.json()["analysis"]["classification_method"]
                    == "self_trained_pipeline"
                )
                prompt = requests.get(
                    base + "/prompts/timetable", headers=headers, timeout=10
                )
                prompt.raise_for_status()
                assert "student_context" in prompt.json()["schema"]["properties"]
                tasks = requests.get(
                    base + "/records/assignment", headers=headers, timeout=10
                ).json()
                assert tasks[0]["due_at"] == "2026-10-25T17:00:00+05:30"
                block = requests.post(
                    base + "/calendar/items",
                    headers=headers,
                    json={
                        "title": "Study",
                        "start": "2026-10-25T09:00",
                        "end": "2026-10-25T10:00",
                    },
                    timeout=10,
                )
                block.raise_for_status()
                assert block.json()["start"].endswith("+05:30")
                identity = requests.post(
                    base + "/profile/facts",
                    headers=headers,
                    json={"field": "roll_number", "value": "23BIT001"},
                    timeout=10,
                )
                identity.raise_for_status()
                ambiguous = requests.post(
                    base + "/marks/extract",
                    headers=headers,
                    json={
                        "course": "NLP201",
                        "assessment": "Quiz",
                        "text": "23BIT001 8/10 9/10",
                    },
                    timeout=10,
                )
                ambiguous.raise_for_status()
                assert ambiguous.json() == []
                assert requests.get(base + "/dashboard", headers=headers, timeout=10).ok
                print(
                    "Frozen sidecar passed: startup, isolated profile, trained inference, exact deadline time, local timezone, ambiguous marks abstention and dashboard."
                )
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                if log.stat().st_size:
                    print(log.read_text()[-8000:])


if __name__ == "__main__":
    main()
