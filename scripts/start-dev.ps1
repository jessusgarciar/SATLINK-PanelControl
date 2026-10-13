[CmdletBinding()]
param(
    [ValidateSet('Orbitium', 'Pendiente')][string]$App = 'Orbitium',
    [switch]$NoBrowser,
    [ValidateSet('Demo', 'Live')][string]$Mode = 'Demo'
)

$ErrorActionPreference = 'Stop'
$taskRepository = Split-Path $PSScriptRoot -Parent
& (Join-Path $taskRepository "$App/scripts/start-dev.ps1") -Mode $Mode -NoBrowser:$NoBrowser
