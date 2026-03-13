param(
    [string[]]$Accounts = @("momentum_5k", "meanrev_5k"),
    [int]$MinTrades = 1,
    [int]$MaxTrades = 5,
    [double]$Fee = 0.0,
    [Nullable[int]]$Seed = $null,
    [switch]$ForceRun,
    [string]$RunSource = "scheduled-daily"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

$logDir = Join-Path $repoRoot "logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$todayTag = Get-Date -Format "yyyyMMdd"
if (-not $ForceRun) {
    $todayLogs = Get-ChildItem -Path $logDir -Filter "daily_paper_trading_${todayTag}_*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending

    if ($todayLogs) {
        $latestToday = $todayLogs | Select-Object -First 1
        $alreadyCompleted = Select-String -Path $latestToday.FullName -Pattern "COMPLETE: Daily paper trading run succeeded." -Quiet
        if ($alreadyCompleted) {
            Write-Output "Daily paper trading already completed today; skipping duplicate run. source=$RunSource"
            exit 0
        }
    }
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logDir "daily_paper_trading_$timestamp.log"
"[$(Get-Date -Format o)] RUN META: source=$RunSource force=$([bool]$ForceRun) accounts=$($Accounts -join ',')" | Tee-Object -FilePath $logPath -Append

function Invoke-Step {
    param(
        [string]$Label,
        [string[]]$Arguments
    )

    "[$(Get-Date -Format o)] START: $Label" | Tee-Object -FilePath $logPath -Append
    & $pythonExe @Arguments 2>&1 | Tee-Object -FilePath $logPath -Append
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Label"
    }
    "[$(Get-Date -Format o)] DONE: $Label" | Tee-Object -FilePath $logPath -Append
}

$accountsCsv = ($Accounts -join ",")

$autoTraderArgs = @(
    "trading/auto_trader.py",
    "--accounts", $accountsCsv,
    "--min-trades", "$MinTrades",
    "--max-trades", "$MaxTrades",
    "--fee", "$Fee"
)
if ($Seed -ne $null) {
    $autoTraderArgs += @("--seed", "$Seed")
}

Push-Location $repoRoot
try {
    Invoke-Step -Label "Auto Trader" -Arguments $autoTraderArgs

    foreach ($account in $Accounts) {
        Invoke-Step -Label "Snapshot $account" -Arguments @("trading/paper_trading.py", "snapshot", "--account", $account)
    }

    Invoke-Step -Label "Compare Strategies" -Arguments @("trading/paper_trading.py", "compare-strategies", "--lookback", "10")

    "[$(Get-Date -Format o)] COMPLETE: Daily paper trading run succeeded." | Tee-Object -FilePath $logPath -Append
}
finally {
    Pop-Location
}
