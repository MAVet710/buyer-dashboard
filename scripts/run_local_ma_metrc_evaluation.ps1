param(
    [Parameter(Mandatory=$true)][string]$Operation,
    [string]$PayloadFile = '',
    [string]$Output = 'artifacts/metrc-evaluation/latest.json',
    [string]$FacilityFamily = '',
    [Parameter(Mandatory=$true)][string]$LicenseNumber,
    [string]$Confirmation = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$bootstrap = Join-Path $PSScriptRoot 'start_local_authenticated.ps1'
if (-not (Test-Path $bootstrap)) {
    throw 'The PC-hosted DoobieLogic bootstrap script is missing: scripts/start_local_authenticated.ps1'
}

# Run the authoritative PC-host bootstrap in this process so DATABASE_URL,
# COMAN_DATABASE_URL, Auth, encryption, and other local-only settings are
# inherited by the evaluation launcher. This does not print or rotate Metrc keys.
. $bootstrap

$env:PYTHONPATH = $root
$python = Join-Path $root '.pilot-venv/Scripts/python.exe'
if (-not (Test-Path $python)) {
    throw 'The PC-hosted DoobieLogic Python runtime is missing: .pilot-venv/Scripts/python.exe'
}

$launcher = Join-Path $PSScriptRoot 'run_local_ma_metrc_evaluation.py'
if (-not (Test-Path $launcher)) {
    throw 'The local MA Metrc evaluation launcher is missing.'
}

$arguments = @(
    $launcher,
    '--operation', $Operation,
    '--output', $Output,
    '--license-number', $LicenseNumber
)
if ($PayloadFile) {
    $arguments += @('--payload-file', $PayloadFile)
}
if ($FacilityFamily) {
    $arguments += @('--facility-family', $FacilityFamily)
}
if ($Confirmation) {
    $arguments += @('--confirmation', $Confirmation)
}

& $python @arguments
exit $LASTEXITCODE
