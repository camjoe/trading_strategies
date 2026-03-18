param(
    [string]$DayOfWeek = "Sunday",
    [string]$Time = "02:00",
    [string]$TaskName = "TradingStrategies_WeeklyDbBackup",
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"

if ($Unregister) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "Scheduled task '$TaskName' removed."
    } else {
        Write-Output "Scheduled task '$TaskName' not found; nothing to remove."
    }
    exit 0
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$scriptPath = Join-Path $repoRoot "trading\scripts\weekly_db_backup.ps1"

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$scriptPath`"" `
    -WorkingDirectory $repoRoot

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $Time

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Weekly SQLite database backup for trading_strategies repo." `
    -Force | Out-Null

Write-Output "Scheduled task '$TaskName' registered."
Write-Output "  Runs: every $DayOfWeek at $Time"
Write-Output "  Script: $scriptPath"
Write-Output ""
Write-Output "To remove it later:"
Write-Output "  .\register-weekly-backup.ps1 -Unregister"
