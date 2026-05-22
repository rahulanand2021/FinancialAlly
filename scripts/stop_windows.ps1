# Stop and remove the FinAlly Docker container (Windows PowerShell).
# Usage: .\scripts\stop_windows.ps1
#
# The named volume is preserved so portfolio data persists between runs.

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$Container = 'finally'

$running = docker ps --format '{{.Names}}'
if ($running -contains $Container) {
    docker stop $Container | Out-Null
}

$existing = docker ps -a --format '{{.Names}}'
if ($existing -contains $Container) {
    docker rm $Container | Out-Null
    Write-Host "Container $Container stopped and removed (volume preserved)."
} else {
    Write-Host "Container $Container is not present."
}
