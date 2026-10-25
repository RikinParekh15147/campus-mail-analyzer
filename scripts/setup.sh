#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
setup_python="${CAMPUS_SETUP_PYTHON:-python3.12}"
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--backend-only" ) ]]; then
  echo 'Usage: bash scripts/setup.sh [--backend-only]' >&2
  exit 2
fi
"$setup_python" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else "Setup requires Python 3.12; select it with CAMPUS_SETUP_PYTHON.")'
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else "Existing .venv uses another Python. Move it aside before setup.")'
fi
"$setup_python" -m venv .venv
.venv/bin/python -m pip install --index-url https://pypi.org/simple -c requirements-dev.constraints -e '.[dev]'
.venv/bin/python -m pip check
.venv/bin/python -m campusmail doctor
if [[ "${1:-}" != "--backend-only" ]]; then
  npm --prefix desktop ci
  npm --prefix desktop run build
fi
echo 'Ready. Private data and trained models are optional for development. Run .venv/bin/python -m pytest -q; start the built desktop with npm --prefix desktop start.'
