<#
.SYNOPSIS
    Registers a Windows Task Scheduler task that runs job_loop.py persistently.

.DESCRIPTION
    Creates one scheduled task ("JustHireMe_JobWatcher") with TWO triggers:
      - At log-on (starts the watcher when you sign in)
      - Every -IntervalHours (a self-healing check: if the watcher already
        crashed/exited, this relaunches it; if it's still running, Task
        Scheduler's own MultipleInstances=IgnoreNew policy makes this a no-op)

    job_loop.py itself loops forever internally (see job_loop.py --interval),
    so the periodic trigger is a safety net, not the only thing driving cycles.

    Uses backend/.venv/Scripts/python.exe (never a system/global python).
    stdout+stderr are appended to backend/logs/job_loop.log (Task Scheduler
    detaches stdio, so without this redirection the logs go nowhere).

.PARAMETER IntervalHours
    Hours between full scrape/score/verify/draft cycles. Default 6. Passed to job_loop.py
    --interval AND used as the watchdog trigger's repetition interval.

.PARAMETER TaskName
    Scheduled task name. Default JustHireMe_JobWatcher. Override for a test run.

.EXAMPLE
    powershell -File backend\scripts\install_watcher.ps1
    powershell -File backend\scripts\install_watcher.ps1 -IntervalHours 4
#>
param(
    [double]$IntervalHours = 6,
    [string]$TaskName = "JustHireMe_JobWatcher"
)

$ErrorActionPreference = "Stop"

$ScriptsDir  = $PSScriptRoot
$BackendDir  = Split-Path $ScriptsDir -Parent
$PythonExe   = Join-Path $BackendDir ".venv\Scripts\python.exe"
$LoopScript  = Join-Path $ScriptsDir "job_loop.py"
$LogDir      = Join-Path $BackendDir "logs"
$LogFile     = Join-Path $LogDir "job_loop.log"

if (-not (Test-Path $PythonExe)) {
    throw "Python venv not found at $PythonExe -- run this from a checkout with backend/.venv set up."
}
if (-not (Test-Path $LoopScript)) {
    throw "job_loop.py not found at $LoopScript"
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Task Scheduler XML (schtasks /Create /XML): two triggers on one action.
# ExecutionTimeLimit=PT0S = no time limit (job_loop.py runs for hours by
# design; Task Scheduler's default 72h limit would otherwise kill it).
# Wrapped in cmd.exe /c because <Exec> has no shell redirection of its own.
# The doubled leading quote (`c "" ...`) is the standard cmd.exe /c quoting
# trick for "quoted program path, followed by unquoted redirection".
$Iso = "PT" + [int]$IntervalHours + "H"
$CmdArgs = "/c `"`"$PythonExe`" `"$LoopScript`" --interval $IntervalHours --cycle-timeout-minutes 4 >> `"$LogFile`" 2>&1`""
# XML text content must escape & (the only mandatory one our value can contain).
$CmdArgsXml = $CmdArgs.Replace('&', '&amp;')
# A LogonTrigger with no <UserId> registers as "any user's logon", which
# Task Scheduler refuses to create for a non-admin caller (ERROR: Access is
# denied) -- confirmed by hand while writing this script. Scoping it to the
# CURRENT user is both what we want (only start it for the person who
# installed it) and what avoids needing elevation.
$UserId = "$env:USERDOMAIN\$env:USERNAME"
$TaskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>JustHireMe continuous job loop (scrape, score, verify, draft; every $IntervalHours h)</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>$UserId</UserId>
    </LogonTrigger>
    <TimeTrigger>
      <Repetition>
        <Interval>$Iso</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2026-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>cmd.exe</Command>
      <Arguments>$CmdArgsXml</Arguments>
      <WorkingDirectory>$BackendDir</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

$XmlPath = Join-Path $env:TEMP "$TaskName-$([guid]::NewGuid()).xml"
# schtasks /XML requires UTF-16LE with BOM, matching the encoding declared above.
[System.IO.File]::WriteAllText($XmlPath, $TaskXml, [System.Text.Encoding]::Unicode)
try {
    schtasks /Create /TN $TaskName /XML $XmlPath /F
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks /Create failed with exit code $LASTEXITCODE"
    }
} finally {
    Remove-Item -Force $XmlPath -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Registered '$TaskName' -- runs at logon, watchdog every ${IntervalHours}h."
Write-Host "Logs: $LogFile"
Write-Host ""
Write-Host "Start it now:   schtasks /Run /TN $TaskName"
Write-Host "Check status:   schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host "Remove it:      powershell -File `"$ScriptsDir\uninstall_watcher.ps1`""
Write-Host "(LogonType=InteractiveToken: it only runs while you're logged in. For"
Write-Host " 'run whether logged on or not', re-register with a stored credential --"
Write-Host " out of scope for a personal dev-machine watcher.)"
