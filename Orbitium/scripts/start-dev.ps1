[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [ValidateSet('Demo', 'Live')][string]$Mode = 'Demo'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$taskRoot = Split-Path $PSScriptRoot -Parent
$taskPython = Join-Path $taskRoot 'backend/.venv/Scripts/python.exe'
$taskRepository = Split-Path $taskRoot -Parent
$taskPgRoot = Join-Path $taskRepository '.local/postgresql'
$taskPgBin = Join-Path $taskPgRoot 'pgsql/bin'
$taskPgData = Join-Path $taskPgRoot 'data'
$taskBackendPort = 8000
$taskFrontendPort = 5173
$taskLogs = Join-Path $taskRoot '.local/dev-logs'
$taskProcesses = @()
$taskLogReaders = @()
$taskVariables = @('SATLINK_DEMO_PREDICTION_ENABLED', 'SATLINK_MQTT_ENABLED', 'VITE_DEMO_PREDICTION', 'VITE_DATA_SOURCE', 'VITE_MISSION_ID', 'SATLINK_PORT', 'SATLINK_BACKEND_ORIGIN', 'PYTHONUNBUFFERED', 'PYTHONIOENCODING')
$taskPrevious = @{}
foreach ($taskName in $taskVariables) { $taskPrevious[$taskName] = [Environment]::GetEnvironmentVariable($taskName, 'Process') }

function Add-TaskLog([string]$Path, [string]$Component, [ConsoleColor]$Color, [switch]$FromEnd) {
    $taskStream = [System.IO.FileStream]::new($Path, [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::Read, ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete))
    if ($FromEnd) { $taskStream.Seek(0, [System.IO.SeekOrigin]::End) | Out-Null }
    $script:taskLogReaders += @{ Reader = [System.IO.StreamReader]::new($taskStream, [System.Text.Encoding]::UTF8);
        Component = $Component; Color = $Color; Pending = '' }
}

function Show-TaskLogs([switch]$Flush) {
    foreach ($taskLog in $taskLogReaders) {
        $taskText = $taskLog.Pending + $taskLog.Reader.ReadToEnd()
        $taskLines = $taskText -split "`n"
        $taskLog.Pending = $taskLines[-1]
        for ($taskLineIndex = 0; $taskLineIndex -lt $taskLines.Count - 1; $taskLineIndex++) {
            $taskLine = $taskLines[$taskLineIndex].TrimEnd("`r")
            if ($taskLine) { Write-Host "[$($taskLog.Component)] $taskLine" -ForegroundColor $taskLog.Color }
        }
        if ($Flush -and $taskLog.Pending) {
            Write-Host "[$($taskLog.Component)] $($taskLog.Pending)" -ForegroundColor $taskLog.Color
            $taskLog.Pending = ''
        }
    }
}

function Wait-TaskUrl([string]$Url, [System.Diagnostics.Process]$Process) {
    for ($taskAttempt = 0; $taskAttempt -lt 60; $taskAttempt++) {
        Show-TaskLogs
        if ($Process.HasExited) { throw "El componente se cerró. Revisa los registros en $taskLogs" }
        try {
            $taskResponse = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing
            if ($taskResponse.StatusCode -eq 200) { return }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    throw "No respondió $Url. Revisa los registros en $taskLogs"
}

try {
    foreach ($taskPath in @($taskPython, "$taskPgBin/pg_ctl.exe", "$taskRoot/frontend/node_modules/vite/bin/vite.js", "$taskRoot/backend/.env")) {
        if (!(Test-Path -LiteralPath $taskPath)) { throw "Falta $taskPath. Consulta los requisitos del README." }
    }
    $taskNode = (Get-Command node -ErrorAction Stop).Source
    $taskListeningPorts = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | ForEach-Object { $_.Port }
    foreach ($taskPort in @($taskBackendPort, $taskFrontendPort)) {
        if ($taskPort -in $taskListeningPorts) {
            throw "El puerto $taskPort está ocupado. Detén el servidor anterior antes de iniciar SATLINK." 
        }
    }
    New-Item -ItemType Directory -Path $taskLogs -Force | Out-Null
    if ($Mode -eq 'Live') {
        $taskMissionFile = Join-Path $taskRoot 'backend/mission.local.json'
        if (!(Test-Path -LiteralPath $taskMissionFile)) { throw "Falta $taskMissionFile." }
        $taskMission = Get-Content -LiteralPath $taskMissionFile -Raw | ConvertFrom-Json
        $env:SATLINK_DEMO_PREDICTION_ENABLED = 'false'
        # Settings carga MQTT desde backend/.env, sin heredar el override de la demo.
        Remove-Item Env:SATLINK_MQTT_ENABLED -ErrorAction SilentlyContinue
        $env:VITE_DATA_SOURCE = 'live'
        $env:VITE_MISSION_ID = [string]$taskMission.id
        $env:VITE_DEMO_PREDICTION = 'local'
    } else {
        $env:SATLINK_DEMO_PREDICTION_ENABLED = 'true'
        $env:SATLINK_MQTT_ENABLED = 'false'
        $env:VITE_DEMO_PREDICTION = 'tawhiri'
        $env:VITE_DATA_SOURCE = 'demo'
    }
    $env:SATLINK_PORT = [string]$taskBackendPort
    $env:SATLINK_BACKEND_ORIGIN = "http://127.0.0.1:$taskBackendPort"
    $env:PYTHONUNBUFFERED = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    # El lanzador administra únicamente el PostgreSQL portátil de este proyecto.
    Push-Location "$taskRoot/backend"
    try {
        & $taskPython -c "from app.bootstrap.config import Settings; from sqlalchemy.engine import make_url; u=make_url(Settings.from_env().database_url); assert u.host in ('127.0.0.1','localhost') and u.port == 5433, 'El arranque local requiere PostgreSQL en localhost:5433'"
        if ($LASTEXITCODE -ne 0) { throw 'La configuración local no es válida.' }
        if ($Mode -eq 'Live') {
            & $taskPython -c "import json; from pathlib import Path; from app.presentation.schemas.api import MissionConfig; from app.bootstrap.config import Settings; c=MissionConfig.model_validate(json.loads(Path('mission.local.json').read_text(encoding='utf-8-sig'))); s=Settings.from_env(); assert c.source == s.source, 'El origen de la mision no coincide'; print('[MISION]', c.name, c.id); print('[MQTT]', 'habilitado' if s.mqtt_enabled else 'deshabilitado: pendiente configurar broker y confirmar payload')"
            if ($LASTEXITCODE -ne 0) { throw 'La configuración de la misión no es válida.' }
        }
    } finally { Pop-Location }
    Write-Host '[BD] Comprobando PostgreSQL…' -ForegroundColor Magenta
    Add-TaskLog "$taskPgRoot/server.log" 'BD' Magenta -FromEnd
    & "$taskPgBin/pg_isready.exe" -h 127.0.0.1 -p 5433 -U satlink_dev -d postgres | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & "$taskPgBin/pg_ctl.exe" -D $taskPgData -l "$taskPgRoot/server.log" -w start
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo iniciar PostgreSQL.' }
    }
    Show-TaskLogs
    Write-Host '[MIGRACIONES] Preparando la base de datos…' -ForegroundColor Yellow
    Push-Location "$taskRoot/backend"
    try {
        & $taskPython -c "from app.bootstrap.config import Settings; from sqlalchemy.engine import make_url; import psycopg; from psycopg import sql; u=make_url(Settings.from_env().database_url); c=psycopg.connect(host=u.host, port=u.port, user=u.username, password=u.password, dbname='postgres', autocommit=True); exists=c.execute('SELECT 1 FROM pg_database WHERE datname=%s', (u.database,)).fetchone(); exists or c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(u.database))); c.close()"
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar la base local de esta aplicación.' }
        & $taskPython -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw 'Falló la preparación de la base de datos.' }
        if ($Mode -eq 'Live') {
            & $taskPython -m app.bootstrap.cli init-mission --file mission.local.json
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo registrar la misión; no se sobrescriben misiones existentes.' }
        }
    } finally { Pop-Location }
    $taskBackend = Start-Process -FilePath $taskPython -ArgumentList '-m', 'app.bootstrap.cli', 'serve' -WorkingDirectory "$taskRoot/backend" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$taskLogs/backend.log" -RedirectStandardError "$taskLogs/backend-error.log"
    $taskProcesses += $taskBackend
    Add-TaskLog "$taskLogs/backend.log" 'BACKEND' Cyan
    Add-TaskLog "$taskLogs/backend-error.log" 'BACKEND · STDERR' DarkCyan
    if ($Mode -eq 'Live') {
        Wait-TaskUrl "http://127.0.0.1:$taskBackendPort/api/v1/missions/$($taskMission.id)/dashboard" $taskBackend
    } else {
        Wait-TaskUrl "http://127.0.0.1:$taskBackendPort/api/v1/demo/predictions" $taskBackend
    }
    $taskFrontend = Start-Process -FilePath $taskNode -ArgumentList 'node_modules/vite/bin/vite.js', '--host', '0.0.0.0', '--port', ([string]$taskFrontendPort), '--strictPort' -WorkingDirectory "$taskRoot/frontend" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$taskLogs/frontend.log" -RedirectStandardError "$taskLogs/frontend-error.log"
    $taskProcesses += $taskFrontend
    Add-TaskLog "$taskLogs/frontend.log" 'FRONTEND' Green
    Add-TaskLog "$taskLogs/frontend-error.log" 'FRONTEND · STDERR' Yellow
    Wait-TaskUrl "http://127.0.0.1:$taskFrontendPort" $taskFrontend
    Write-Host "SATLINK / ORBITIUM listo: http://127.0.0.1:$taskFrontendPort"
    if ($Mode -eq 'Live') {
        Write-Host "Estación real: $($taskMission.name). MQTT usa backend/.env; sin uplinks no hay telemetría."
    } else {
        Write-Host "Demo visual + Tawhiri real. Consultas manuales desde Recuperación."
    }
    Write-Host "Registros: $taskLogs · Ctrl+C para detener."
    Write-Host 'Logs en vivo: [BD], [BACKEND] y [FRONTEND]. Tawhiri aparece en las solicitudes del backend.'
    if (!$NoBrowser) { Start-Process "http://127.0.0.1:$taskFrontendPort" }
    while (!$taskBackend.HasExited -and !$taskFrontend.HasExited) {
        Show-TaskLogs
        Start-Sleep -Milliseconds 200
    }
    Show-TaskLogs -Flush
    throw "Un componente se detuvo. Revisa $taskLogs"
} finally {
    foreach ($taskProcess in $taskProcesses) {
        if (!$taskProcess.HasExited) { Stop-Process -Id $taskProcess.Id -ErrorAction SilentlyContinue }
    }
    # PostgreSQL es infraestructura local compartida; permanece activo para la otra webapp.
    try { Show-TaskLogs -Flush } finally {
        foreach ($taskLog in $taskLogReaders) { $taskLog.Reader.Dispose() }
    }
    foreach ($taskName in $taskVariables) { [Environment]::SetEnvironmentVariable($taskName, $taskPrevious[$taskName], 'Process') }
}
