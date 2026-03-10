param(
    [int]$Port = 8080,
    [switch]$Foreground
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogsDir = Join-Path $RepoRoot "logs"
$LogPath = Join-Path $RepoRoot "logs\dashboard.log"
$PidPath = Join-Path $LogsDir "dashboard.pid"

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

$listener = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    Write-Host "Port $Port is already in use by PID $($listener.OwningProcess)."
    Write-Host "If this is the dashboard, open: http://127.0.0.1:$Port"
    exit 0
}

$uvicornCmd = "uv run uvicorn server_monitor.dashboard.main:build_dashboard_app --factory --host 127.0.0.1 --port $Port"

if ($Foreground) {
    Set-Location $RepoRoot
    Write-Host "Starting dashboard in foreground on http://127.0.0.1:$Port"
    Invoke-Expression $uvicornCmd
    exit $LASTEXITCODE
}

$wrappedCommand = "Set-Location '$RepoRoot'; $uvicornCmd *> '$LogPath'"
$proc = Start-Process -FilePath "powershell.exe" `
    -WindowStyle Hidden `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $wrappedCommand) `
    -PassThru

$proc.Id | Set-Content -Path $PidPath -Encoding utf8

Write-Host "Dashboard started in background."
Write-Host "PID: $($proc.Id)"
Write-Host "URL: http://127.0.0.1:$Port"
Write-Host "Log: $LogPath"
