[CmdletBinding()]
param(
    [string]$WorkspacePath = "$env:USERPROFILE\AI\bandi-qwen"
)

$ErrorActionPreference = "Stop"
$taskName = "Bandi Qwen Branch Sync"
$scriptPath = Join-Path $PSScriptRoot "sync-qwen-branch.ps1"

if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Qwen branch sync script is missing."
}
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw "Scheduled task already exists: $taskName"
}

$arguments = "-NoProfile -File `"$scriptPath`" -WorkspacePath `"$WorkspacePath`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Daily -At "12:00AM"
$trigger.Repetition.Interval = "PT5M"
$trigger.Repetition.Duration = "P1D"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Description "Pushes committed Bandi Qwen agent-branch work to GitHub every five minutes." | Out-Null
Write-Output "Installed scheduled task: $taskName"
