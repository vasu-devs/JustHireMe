<#
.SYNOPSIS
    Removes the watch_jobs.py scheduled task registered by install_watcher.ps1.

.EXAMPLE
    powershell -File backend\scripts\uninstall_watcher.ps1
#>
param(
    [string]$TaskName = "JustHireMe_JobWatcher"
)

$existing = schtasks /Query /TN $TaskName 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "No task named '$TaskName' is registered -- nothing to do."
    exit 0
}

schtasks /Delete /TN $TaskName /F
if ($LASTEXITCODE -ne 0) {
    throw "schtasks /Delete failed with exit code $LASTEXITCODE"
}
Write-Host "Removed scheduled task '$TaskName'."
Write-Host "(watch_jobs.py itself is not killed if it's already running in a"
Write-Host " foreground terminal -- Ctrl-C that separately if needed.)"
