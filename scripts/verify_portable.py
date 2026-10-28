"""Run portable delivery checks and save machine/lock/commit evidence."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from uuid import uuid4


PROJECT = Path(__file__).resolve().parents[1]


def _sha(path):
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command, *, cwd, timeout, log):
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True,
                                text=True, timeout=timeout, check=False)
        log.write_text(result.stdout + "\n[stderr]\n" + result.stderr,
                       encoding="utf-8")
        return {"status": "passed" if result.returncode == 0 else "failed",
                "exit_code": result.returncode, "command": command}
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        return {"status": "failed", "exit_code": None, "command": command}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop-workflow", action="store_true",
                        help="also run the real Electron/Python workflow")
    args = parser.parse_args()
    python = PROJECT / (".venv-win/Scripts/python.exe" if os.name == "nt"
                        else ".venv/bin/python")
    if not python.is_file():
        parser.error(f"Isolated Python is missing: {python}")
    npm = "npm.cmd" if os.name == "nt" else "npm"
    npx = "npx.cmd" if os.name == "nt" else "npx"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = stamp + "-" + uuid4().hex[:8]
    directory = PROJECT / "artifacts/verification" / run_id
    directory.mkdir(parents=True, exist_ok=False)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT,
                            capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT,
                           capture_output=True, text=True, check=True).stdout
    locks = {name: _sha(PROJECT / name) for name in
             ("pyproject.toml", "requirements-dev.constraints",
              "desktop/package-lock.json")}
    checks = {
        "versions": ([str(python), "-c",
                      "import json,platform,sys; import numpy,scipy,sklearn; "
                      "print(json.dumps({'python':sys.version.split()[0],"
                      "'numpy':numpy.__version__,'scipy':scipy.__version__,"
                      "'scikit_learn':sklearn.__version__,'platform':platform.platform()}))"],
                     PROJECT, 30),
        "doctor": ([str(python), "-m", "campusmail", "doctor"], PROJECT, 90),
        "python_tests": ([str(python), "-m", "pytest", "-q", "-m", "not research"],
                         PROJECT, 300),
        "bridge_tests": ([npm, "test"], PROJECT / "desktop", 120),
        "frontend_build": ([npm, "run", "build"], PROJECT / "desktop", 180),
    }
    if args.desktop_workflow:
        checks["desktop_workflow"] = ([npx, "playwright", "test",
                                       "tests/desktop.spec.cjs", "--reporter=line"],
                                      PROJECT / "desktop", 180)
    results = {name: _run(command, cwd=cwd, timeout=timeout,
                          log=directory / f"{name}.log")
               for name, (command, cwd, timeout) in checks.items()}
    versions = None
    if results["versions"]["status"] == "passed":
        try:
            versions = json.loads((directory / "versions.log").read_text(encoding="utf-8")
                                  .splitlines()[0])
        except (ValueError, IndexError):
            results["versions"]["status"] = "failed"
    report = {
        "schema_version": "portable-verification-v1", "run_id": run_id,
        "created_utc": stamp, "commit": commit,
        "working_tree_dirty": bool(dirty),
        "machine": {"system": platform.system(), "release": platform.release(),
                    "machine": platform.machine(), "node": platform.node()},
        "environment_versions": versions,
        "lock_sha256": locks, "checks": results,
    }
    (directory / "run.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                        encoding="utf-8")
    print(json.dumps({"run_id": run_id, "report": str(directory / "run.json"),
                      "checks": {name: value["status"] for name, value in results.items()}},
                     sort_keys=True))
    return 0 if all(value["status"] == "passed" for value in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
