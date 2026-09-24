# OuroTaurus Shift Automation — Quick Start
# Usage:
#   .\start_shift_automation.ps1            # run master scheduler once
#   .\start_shift_automation.ps1 -Install   # register Windows scheduled tasks (admin)

param([switch]$Install)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Py = 'python3'
$Master = Join-Path $ScriptDir 'master_shift_scheduler.py'

function Test-Command($cmd) { Get-Command $cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source }
if (-not (Test-Command 'python3')) { Write-Error 'python3 not found on PATH'; exit 1 }

if ($Install) {
    Write-Host '[setup] Creating Windows Task Scheduler entries...' -ForegroundColor Cyan
    $taskName = 'OuroTaurus_Shift_Master'
    $action = New-ScheduledTaskAction -Execute 'python3' -Argument "`"$Master`""
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15)
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'OuroTaurus master shift dispatcher' -Force | Out-Null
    Write-Host '[setup] Registered OuroTaurus_Shift_Master every 15 min.' -ForegroundColor Green
    exit 0
}

& $Py $Master
