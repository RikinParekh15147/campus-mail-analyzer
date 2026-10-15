#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --index-url https://pypi.org/simple -e '.[dev]'
npm --prefix desktop ci
npm --prefix desktop run build
echo 'Ready. Train models with .venv/bin/python -m campusmail train --task academic, then start with npm --prefix desktop start.'
