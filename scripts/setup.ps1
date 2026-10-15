$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
python -m venv .venv-win
& .\.venv-win\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -e '.[dev]'
npm --prefix desktop ci
npm --prefix desktop run build
Write-Output 'Ready. Train the academic and actionability models with .venv-win\Scripts\python.exe -m campusmail train --task TASK. Start with npm --prefix desktop start.'
