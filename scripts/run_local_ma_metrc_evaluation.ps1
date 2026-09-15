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

# Normalize Windows-created JSON to UTF-8 without BOM before the Python runner
# reads it. Validate the JSON here so malformed files fail before credential
# resolution or provider preflight.
$normalizedPayload = $PayloadFile
if ($PayloadFile) {
    $payloadPath = [System.IO.Path]::GetFullPath((Join-Path $root $PayloadFile))
    if (-not (Test-Path $payloadPath)) {
        throw "Payload file does not exist: $PayloadFile"
    }
    $payloadText = [System.IO.File]::ReadAllText($payloadPath)
    try {
        $payloadObject = $payloadText | ConvertFrom-Json
    } catch {
        throw 'Payload file is not valid JSON.'
    }
    if ($Operation -eq 'package_create') {
        $location = [string]$payloadObject.location
        if ([string]::IsNullOrWhiteSpace($location)) {
            throw 'Package create requires location. Metrc previously rejected this evaluation request with HTTP 400 because Location was omitted.'
        }
    }
    [System.IO.File]::WriteAllText(
        $payloadPath,
        ($payloadObject | ConvertTo-Json -Depth 30),
        (New-Object System.Text.UTF8Encoding($false))
    )
    $normalizedPayload = $payloadPath
}

$arguments = @(
    $launcher,
    '--operation', $Operation,
    '--output', $Output,
    '--license-number', $LicenseNumber
)
if ($normalizedPayload) {
    $arguments += @('--payload-file', $normalizedPayload)
}
if ($FacilityFamily) {
    $arguments += @('--facility-family', $FacilityFamily)
}
if ($Confirmation) {
    $arguments += @('--confirmation', $Confirmation)
}

& $python @arguments
exit $LASTEXITCODE
