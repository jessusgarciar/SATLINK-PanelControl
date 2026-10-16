[CmdletBinding()]
param(
    [ValidateRange(1, 10000)][int]$Samples = 10,
    [ValidateRange(1, 86400)][int]$TimeoutSeconds = 600,
    [string]$Report
)

$ErrorActionPreference = 'Stop'
$appRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $appRoot 'backend/.venv/Scripts/python.exe'
$backend = Join-Path $appRoot 'backend'
if (!(Test-Path -LiteralPath $python)) { throw "Falta el entorno virtual: $python" }
if (!$Report) {
    $logs = Join-Path $appRoot '.local/dev-logs'
    if (!(Test-Path -LiteralPath $logs)) {
        if (!(Test-Path -LiteralPath $appRoot -PathType Container)) { throw 'No existe la carpeta de Orbitium.' }
        New-Item -ItemType Directory -Path $logs -Force | Out-Null
    }
    $Report = Join-Path $logs 'telemetry-check.json'
} else {
    $Report = [System.IO.Path]::GetFullPath($Report)
    if (!(Test-Path -LiteralPath (Split-Path $Report -Parent) -PathType Container)) {
        throw 'La carpeta del informe debe existir.'
    }
}

Push-Location $backend
try {
    & $python -m app.bootstrap.cli check-live --samples $Samples --timeout $TimeoutSeconds --report $Report
    $result = $LASTEXITCODE
} finally { Pop-Location }
Write-Host "Informe local: $Report"
exit $result
