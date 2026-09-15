param(
    [string]$RunId = '',
    [string]$Output = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$bootstrap = Join-Path $PSScriptRoot 'start_local_authenticated.ps1'
if (-not (Test-Path $bootstrap)) {
    throw 'The PC-hosted DoobieLogic bootstrap script is missing: scripts/start_local_authenticated.ps1'
}

# Dot-source the existing PC-host bootstrap so this PowerShell process receives
# the same local database/Auth/encryption configuration as FastAPI. The bootstrap
# starts only missing local services and does not rotate Metrc credentials.
. $bootstrap

$python = Join-Path $root '.pilot-venv/Scripts/python.exe'
if (-not (Test-Path $python)) {
    throw 'The PC-hosted DoobieLogic Python runtime is missing: .pilot-venv/Scripts/python.exe'
}

# Python invoked by script path normally places only scripts\ on sys.path. Add
# the repository root explicitly so backend/, modules/, and services/ resolve in
# the same way they do when the application is started from the repo root.
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$root;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $root
}

$arguments = @((Join-Path $PSScriptRoot 'run_local_metrc_execution_precheck.py'))
if ($RunId) {
    $arguments += @('--run-id', $RunId)
}
if ($Output) {
    $arguments += @('--output', $Output)
}

& $python @arguments
exit $LASTEXITCODE
