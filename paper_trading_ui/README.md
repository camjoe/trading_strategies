# Paper Trading Web UI

A separate scaffold for viewing paper trading accounts, snapshots, trades, and log files.

## Environment Setup

From repository root:

```powershell
Copy-Item paper_trading_ui/backend/.env.example paper_trading_ui/backend/.env
Copy-Item paper_trading_ui/frontend/.env.example paper_trading_ui/frontend/.env
```

Backend env file supports:

- `API_HOST` (used by run command examples)
- `API_PORT` (used by run command examples)
- `CORS_ORIGINS` (comma-separated or `*`)
- `LOGS_DIR` (optional override for logs directory)

Frontend env file supports:

- `VITE_API_BASE` (API base URL, default `http://127.0.0.1:8000`)

## Backend (FastAPI)

From repository root:

```powershell
pip install -r paper_trading_ui/backend/requirements.txt
Get-Content paper_trading_ui/backend/.env | ForEach-Object {
	if ($_ -match '^(?!#)([^=]+)=(.*)$') {
		[Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
	}
}
uvicorn paper_trading_ui.backend.main:app --reload --host $env:API_HOST --port ([int]$env:API_PORT)
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

## Available API Routes

- `GET /health`
- `GET /api/accounts`
- `GET /api/accounts/{account_name}`
- `GET /api/logs/files`
- `GET /api/logs/{file_name}?limit=400&contains=error`
- `POST /api/actions/snapshot/{account_name}`
- `POST /api/actions/snapshot-all`
