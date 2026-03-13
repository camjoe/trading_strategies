# Paper Trading Scheduler

This document contains all PowerShell and Task Scheduler operations for automated paper trading runs.

## Runner Script

Script path:
- `trading/daily_paper_trading.ps1`

Behavior:
- Runs auto-trader for configured accounts.
- Saves snapshots.
- Prints strategy comparison.
- Writes logs to `logs/`.
- Writes run metadata including trigger source (`RunSource`) in each log.
- Prevents duplicate successful runs on the same date unless `-ForceRun` is used.

## Manual Runs

```powershell
# Normal run
powershell -NoProfile -ExecutionPolicy Bypass -File .\trading\daily_paper_trading.ps1 -RunSource manual

# Force extra same-day run
powershell -NoProfile -ExecutionPolicy Bypass -File .\trading\daily_paper_trading.ps1 -RunSource manual -ForceRun
```

## Scheduled Tasks (No Elevation Approach)

Use two tasks instead of rewriting one task with multiple triggers:
- Daily task: `Trading\DailyPaperTrading`
- Startup fallback task: `Trading\DailyPaperTradingFallback`

If Task Scheduler creation is blocked by permissions in your environment, use the Startup-folder fallback below.

Create startup fallback task (runs 10 minutes after boot):

```powershell
$scriptPath = Join-Path (Get-Location) "trading\daily_paper_trading.ps1"
$action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
schtasks /Create /TN "Trading\DailyPaperTradingFallback" /SC ONSTART /DELAY 0000:10 /TR $action /F
```

Query both tasks:

```powershell
schtasks /Query /TN "Trading\DailyPaperTrading" /V /FO LIST
schtasks /Query /TN "Trading\DailyPaperTradingFallback" /V /FO LIST
```

Change daily run time:

```powershell
schtasks /Change /TN "Trading\DailyPaperTrading" /ST 15:45
```

Delete fallback task:

```powershell
schtasks /Delete /TN "Trading\DailyPaperTradingFallback" /F
```

## Startup Folder Fallback (No Elevation)

This runs once at user logon and works without admin rights.

```powershell
$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$repoRoot = Get-Location
$cmdPath = Join-Path $startupDir "daily_paper_trading_fallback.cmd"
$content = "@echo off`r`ncd /d `"$repoRoot`"`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File .\trading\daily_paper_trading.ps1 -RunSource startup-fallback`r`n"
Set-Content -Path $cmdPath -Value $content -Encoding ASCII
```

Because `trading/daily_paper_trading.ps1` has same-day duplicate protection, logon fallback and daily scheduled runs can coexist safely.

## Elevated Option (Optional)

If you want one task with both daily + startup triggers on the same task definition, run PowerShell as Administrator and use the ScheduledTasks cmdlets with `Register-ScheduledTask`.
