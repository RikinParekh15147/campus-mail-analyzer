"""Setup stops at a failed native command before changing the environment."""

import os
from pathlib import Path
import subprocess
import sys


def test_setup_reports_missing_python_without_installing(tmp_path):
    project = Path(__file__).resolve().parents[1]
    missing = str(tmp_path / "missing-python")
    if sys.platform == "win32":
        command = ["pwsh", "-NoProfile", "-File", str(project / "scripts/setup.ps1"),
                   "-Python", missing, "-BackendOnly"]
        expected = "missing-python"
    else:
        command = ["bash", str(project / "scripts/setup.sh"), "--backend-only"]
        expected = "missing-python"
    environment = {**os.environ, "CAMPUS_SETUP_PYTHON": missing}
    result = subprocess.run(command, cwd=tmp_path, env=environment,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert expected in result.stdout + result.stderr
    assert list(tmp_path.iterdir()) == []
