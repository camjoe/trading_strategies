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

## Backend Boundary Notes

- Route modules under `paper_trading_ui/backend/routes/` should stay thin and delegate DB mutations to backend service helpers.
- Backend service modules now live under `paper_trading_ui/backend/services/`.
- Admin account deletion now delegates to canonical runtime data-ops (`trading.interfaces.runtime.data_ops.admin`) through `paper_trading_ui/backend/services/admin.py`.
- New UI/backend code should use canonical runtime data-ops modules (`trading.interfaces.runtime.data_ops.*`).
- Account snapshot history, account-name listing, and recent backtest-run list queries are exposed through backend service helpers instead of inline route SQL.
- Managed-account listing and latest-backtest lookup in backend account services are routed through trading repository adapters.
- Account existence and latest-snapshot lookups in backend DB/test-account services are routed through trading repository adapters.
