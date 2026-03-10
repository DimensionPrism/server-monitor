param()

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidPath = Join-Path $RepoRoot "logs\dashboard.pid"
$stopped = @()

if (Test-Path $PidPath) {
    $pidText = (Get-Content -Path $PidPath -Raw).Trim()
    $targetPid = 0
    if ([int]::TryParse($pidText, [ref]$targetPid)) {
        $process = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
            $stopped += $targetPid
        }
    }
    Remove-Item -Path $PidPath -Force -ErrorAction SilentlyContinue
}

$pattern = "*server_monitor.dashboard.main:build_dashboard_app*"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like $pattern }
foreach ($proc in $procs) {
    if ($stopped -contains $proc.ProcessId) {
        continue
    }
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    $stopped += $proc.ProcessId
}

if ($stopped.Count -eq 0) {
    Write-Host "No dashboard process found."
    exit 0
}

Write-Host "Stopped dashboard process IDs: $($stopped -join ', ')"
