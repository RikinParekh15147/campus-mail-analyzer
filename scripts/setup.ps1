param([string]$Python = 'py', [switch]$BackendOnly)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed with exit code $LASTEXITCODE" }
}
$PythonArgs = @()
if ($Python -eq 'py') { $PythonArgs = @('-3.12') }
$VersionCheck = 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else "Setup requires Python 3.12; select it with -Python.")'
Invoke-Checked $Python ($PythonArgs + @('-c', $VersionCheck))
if (Test-Path '.\.venv-win\Scripts\python.exe') {
    Invoke-Checked '.\.venv-win\Scripts\python.exe' @('-c', $VersionCheck)
}
Invoke-Checked $Python ($PythonArgs + @('-m', 'venv', '.venv-win'))
$VenvPython = '.\.venv-win\Scripts\python.exe'
Invoke-Checked $VenvPython @('-m', 'pip', 'install', '--index-url', 'https://pypi.org/simple', '-c', 'requirements-dev.constraints', '-e', '.[dev]')
Invoke-Checked $VenvPython @('-m', 'pip', 'check')
Invoke-Checked $VenvPython @('-m', 'campusmail', 'doctor')
if (-not $BackendOnly) {
    Invoke-Checked 'npm.cmd' @('--prefix', 'desktop', 'ci')
    Invoke-Checked 'npm.cmd' @('--prefix', 'desktop', 'run', 'build')
}
Write-Output 'Ready. Private data/models are optional for development. Run .\.venv-win\Scripts\python.exe -m pytest -q. Start the built desktop with npm --prefix desktop start.'
