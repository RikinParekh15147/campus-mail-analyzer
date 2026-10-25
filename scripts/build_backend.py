"""Build the Python sidecar for the current operating system only."""

import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
args = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--onedir",
    "--name",
    "campusmail-backend",
    "--paths",
    str(root / "backend"),
    "--distpath",
    str(root / "dist"),
    "--workpath",
    str(root / "build/pyinstaller"),
    "--specpath",
    str(root / "build"),
    "--collect-all",
    "sklearn",
    "--collect-submodules",
    "keyring.backends",
    "--collect-submodules",
    "scipy._external.array_api_compat.numpy",
    "--hidden-import",
    "uvicorn.logging",
    "--hidden-import",
    "uvicorn.loops.asyncio",
    "--hidden-import",
    "uvicorn.protocols.http.h11_impl",
    "--hidden-import",
    "uvicorn.lifespan.on",
    "--exclude-module",
    "pytest",
    "--exclude-module",
    "tkinter",
    "--add-data",
    str(root / "artifacts/models") + ":artifacts/models",
    "--add-data",
    str(root / "prompts") + ":prompts",
    "--add-data",
    str(root / "schemas") + ":schemas",
    "--add-data",
    str(root / "dataset_collections.json") + ":.",
    str(root / "scripts/backend_entry.py"),
]
subprocess.run(args, cwd=root, check=True)
