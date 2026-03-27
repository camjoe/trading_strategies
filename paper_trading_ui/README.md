# Paper Trading Web UI

A separate scaffold for viewing paper trading accounts, snapshots, trades, and log files.

## Environment Setup

Copy the example env files once before first run:

```sh
cp paper_trading_ui/backend/.env.example paper_trading_ui/backend/.env
cp paper_trading_ui/frontend/.env.example paper_trading_ui/frontend/.env
```

Backend env supports `CORS_ORIGINS` and `LOGS_DIR`. Frontend env supports `VITE_API_BASE` (default `http://127.0.0.1:8000`).

## One-Command Launcher

The easiest way to start both services:

```sh
python -m scripts.launch_ui
```

Keeps both attached to your terminal. Press `Ctrl+C` to stop both. Defaults: backend `http://127.0.0.1:8000`, frontend `http://127.0.0.1:5173`.

## Manual Startup

Backend:

```sh
uvicorn paper_trading_ui.backend.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```sh
cd paper_trading_ui/frontend
npm install
npm run dev
```

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
