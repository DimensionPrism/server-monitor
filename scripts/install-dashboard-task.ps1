param(
    [string]$TaskName = "ServerMonitorDashboard",
    [int]$Port = 8080,
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"

$StartScript = Join-Path $PSScriptRoot "start-dashboard.ps1"
if (-not (Test-Path $StartScript)) {
    throw "Missing start script: $StartScript"
}

$actionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" -Port $Port"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArgs
$trigger = New-ScheduledTaskTrigger -AtLogOn

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Description "Starts Server Monitor Dashboard at logon." `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "Scheduled task '$TaskName' installed."

if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Scheduled task '$TaskName' started."
}
