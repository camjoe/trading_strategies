param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Import-EnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )

    if (-not (Test-Path $FilePath)) {
        return
    }

    Get-Content $FilePath | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        if ($line -match "^([A-Za-z_][A-Za-z0-9_]*)=(.*)$") {
            $name = $matches[1]
            $value = $matches[2]
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

$uiDir = Resolve-Path $PSScriptRoot
$repoRoot = Resolve-Path (Join-Path $uiDir "..")
$backendEnv = Join-Path $uiDir "backend/.env"
$frontendEnv = Join-Path $uiDir "frontend/.env"
$pythonExe = Join-Path $repoRoot ".venv/Scripts/python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found at $pythonExe. Activate or create .venv first."
}

Import-EnvFile -FilePath $backendEnv
Import-EnvFile -FilePath $frontendEnv

if (-not $env:API_HOST) { $env:API_HOST = "127.0.0.1" }
if (-not $env:API_PORT) { $env:API_PORT = "8000" }
if (-not $env:VITE_API_BASE) { $env:VITE_API_BASE = "http://$($env:API_HOST):$($env:API_PORT)" }

$backendCmd = "Set-Location '$repoRoot'; & '$pythonExe' -m uvicorn paper_trading_ui.backend.main:app --reload --host $env:API_HOST --port $env:API_PORT"
$frontendCmd = "Set-Location '$($uiDir.Path)/frontend'; npm run dev"

if ($DryRun) {
    Write-Host "Backend command:" -ForegroundColor Cyan
    Write-Host $backendCmd
    Write-Host "Frontend command:" -ForegroundColor Cyan
    Write-Host $frontendCmd
    return
}

Start-Process powershell -WorkingDirectory $repoRoot -ArgumentList @("-NoExit", "-Command", $backendCmd)
Start-Process powershell -WorkingDirectory (Join-Path $uiDir "frontend") -ArgumentList @("-NoExit", "-Command", $frontendCmd)

Write-Host "Launched backend and frontend in new PowerShell windows." -ForegroundColor Green
Write-Host "Backend: http://$($env:API_HOST):$($env:API_PORT)" -ForegroundColor Green
Write-Host "Frontend: check the Vite output window for the URL." -ForegroundColor Green
