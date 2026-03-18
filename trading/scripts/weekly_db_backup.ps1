param(
    [string]$BackupDir = "",
    [switch]$ForceRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

$logDir = Join-Path $repoRoot "local\logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

# Guard: skip if a successful backup already ran this calendar week
$weekTag = (Get-Date).ToString("yyyy_'W'") + (Get-Date -UFormat "%V")
if (-not $ForceRun) {
    $thisWeekLogs = Get-ChildItem -Path $logDir -Filter "weekly_db_backup_${weekTag}_*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending

    if ($thisWeekLogs) {
        $alreadyDone = Select-String -Path ($thisWeekLogs | Select-Object -First 1).FullName `
            -Pattern "COMPLETE: Weekly database backup succeeded." -Quiet
        if ($alreadyDone) {
            Write-Output "Weekly database backup already completed this week; skipping. Use -ForceRun to override."
            exit 0
        }
    }
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logDir "weekly_db_backup_${weekTag}_$timestamp.log"
"[$(Get-Date -Format o)] RUN META: force=$([bool]$ForceRun)" | Tee-Object -FilePath $logPath -Append

$backupArgs = @("-m", "dev_tools.db_admin", "backup-db")
if ($BackupDir -ne "") {
    $backupArgs += @("--destination", $BackupDir)
}

Push-Location $repoRoot
try {
    "[$(Get-Date -Format o)] START: Database backup" | Tee-Object -FilePath $logPath -Append
    & $pythonExe @backupArgs 2>&1 | Tee-Object -FilePath $logPath -Append
    if ($LASTEXITCODE -ne 0) {
        throw "Database backup failed."
    }
    "[$(Get-Date -Format o)] DONE: Database backup" | Tee-Object -FilePath $logPath -Append

    "[$(Get-Date -Format o)] COMPLETE: Weekly database backup succeeded." | Tee-Object -FilePath $logPath -Append
}
catch {
    "[$(Get-Date -Format o)] ERROR: $_" | Tee-Object -FilePath $logPath -Append
    exit 1
}
finally {
    Pop-Location
}
