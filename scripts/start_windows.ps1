# Start the FinAlly Docker container (Windows PowerShell).
# Usage: .\scripts\start_windows.ps1 [-Build]
#
# Builds the image if it does not exist (or if -Build is passed),
# then starts the container with the persistent volume and .env file.

[CmdletBinding()]
param(
    [switch]$Build
)

$ErrorActionPreference = 'Stop'

$Image     = 'finally:latest'
$Container = 'finally'
$Volume    = 'finally-data'
$Port      = 8000
$Url       = "http://localhost:$Port"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ProjectRoot

if (-not (Test-Path (Join-Path $ProjectRoot '.env'))) {
    Write-Error "ERROR: .env not found in $ProjectRoot. Copy .env.example to .env first."
    exit 1
}

$imageExists = $true
try {
    docker image inspect $Image 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { $imageExists = $false }
} catch {
    $imageExists = $false
}

if ($Build -or -not $imageExists) {
    Write-Host "Building image $Image..."
    docker build -t $Image .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$running = docker ps --format '{{.Names}}'
if ($running -contains $Container) {
    Write-Host "Container $Container already running at $Url"
    exit 0
}

$existing = docker ps -a --format '{{.Names}}'
if ($existing -contains $Container) {
    docker rm $Container | Out-Null
}

docker run -d `
    --name $Container `
    --env-file .env `
    -p "$Port`:8000" `
    -v "$Volume`:/app/db" `
    --restart unless-stopped `
    $Image | Out-Null

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "FinAlly started at $Url"
Start-Process $Url | Out-Null
