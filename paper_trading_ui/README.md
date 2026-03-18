# Paper Trading Web UI

A separate scaffold for viewing paper trading accounts, snapshots, trades, and log files.

## Environment Setup

From repository root:

```powershell
Copy-Item paper_trading_ui/backend/.env.example paper_trading_ui/backend/.env
Copy-Item paper_trading_ui/frontend/.env.example paper_trading_ui/frontend/.env
```

Backend env file supports:

- `CORS_ORIGINS` (comma-separated or `*`)
- `LOGS_DIR` (optional override for logs directory)

Frontend env file supports:

- `VITE_API_BASE` (API base URL, default `http://127.0.0.1:8000`)

## Backend (FastAPI)

From repository root:

```powershell
pip install -r requirements/base.txt
Get-Content paper_trading_ui/backend/.env | ForEach-Object {
	if ($_ -match '^(?!#)([^=]+)=(.*)$') {
		[Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
	}
}
uvicorn paper_trading_ui.backend.main:app --reload --host $env:API_HOST --port ([int]$env:API_PORT)
```

Or run directly with local defaults:

```powershell
uvicorn paper_trading_ui.backend.main:app --reload --host 127.0.0.1 --port 8000
```

API base URL: http://127.0.0.1:8000

## Frontend (TypeScript + Vite)

From repository root:

```powershell
cd paper_trading_ui/frontend
npm install
npm run dev
```

Frontend URL (default): http://127.0.0.1:5173

Note: the launcher runs Vite with `--strictPort`, so if `FRONTEND_PORT` is occupied the frontend window will show an explicit error instead of silently switching ports.

## One-Command Launcher (Cross-Platform Python)

From repository root:

```powershell
python paper_trading_ui/scripts/launch_ui.py
```

This keeps both services attached to your terminal and stops both when you press `Ctrl+C`.

## One-Command Launcher (PowerShell)

From repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\paper_trading_ui\scripts\launch-ui.ps1
```

Dry run (show commands without starting processes):

```powershell
powershell -ExecutionPolicy Bypass -File .\paper_trading_ui\scripts\launch-ui.ps1 -DryRun
```

Current Python launcher defaults:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`

## Core API Routes

- `GET /health`
- `GET /api/accounts`
- `GET /api/accounts/{account_name}`
- `GET /api/logs/files`
- `GET /api/logs/{file_name}?limit=400&contains=error`
- `POST /api/actions/snapshot/{account_name}`
- `POST /api/actions/snapshot-all`

For the complete, always-current route list (including backtesting endpoints), see:
- `paper_trading_ui/backend/main.py`
