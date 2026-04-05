# Paper Trading Web UI

A separate scaffold for viewing paper trading accounts, snapshots, trades, and log files.

## Purpose

Provide a local dashboard and API for paper-trading operations, including:

- **Account visibility** — live summary cards and per-account detail (snapshots, trades, backtest metrics).
- **Test Account tab** — dedicated view for the virtual `test_account`, with a manual trade entry form to inject buy/sell records directly into its backing DB account.
- **Alt Strategies tab** — health status of the three alt-strategy feature providers (Policy, News, Social) and on-demand signal lookup for any ticker.
- **Account parameter editing** — inline `strategy` and `risk_policy` updates per account via the account detail panel.
- **Compare view** — side-by-side performance table for all accounts with strategy-filter dropdown.
- **Snapshots and operational logs** — snapshot actions and log-file browsing.

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

## Workflows

1. Start both services with `python -m scripts.launch_ui` for day-to-day usage.
2. Use manual startup commands when working on backend or frontend in isolation.
3. Update this README whenever API routes or UI operational flows change.

## Core API Routes

### Accounts

- `GET /api/accounts` — list all managed accounts plus the virtual test account.
- `GET /api/accounts/compare` — comparison payload for all accounts (used by the Compare tab).
- `GET /api/accounts/{account_name}` — full detail: summary, snapshots, trades, latest backtest.
- `PATCH /api/accounts/{account_name}/params` — update `strategy` and/or `riskPolicy` inline. Body: `AccountParamsRequest`.

### Trades

- `POST /api/accounts/{account_name}/trades` — inject a manual trade record. Body: `ManualTradeRequest` (`ticker`, `side`, `qty`, `price`, `fee`). Routes `test_account` trades to its backing DB account automatically.

### Alt-Strategy Feature Providers

- `GET /api/features/status` — probe all three alt-strategy providers (Policy, News, Social) and return availability + key scores.
- `POST /api/features/signals` — run all three signal functions for a ticker. Body: `FeatureSignalsRequest` (`ticker`). Returns per-strategy `signal`, `available`, and `features`.

### Logs

- `GET /api/logs/files` — list available log files.
- `GET /api/logs/{file_name}?limit=400&contains=error` — tail/filter a log file.

### Actions

- `POST /api/actions/snapshot/{account_name}` — take a snapshot for one account.
- `POST /api/actions/snapshot-all` — snapshot all managed accounts.

### Health

- `GET /health`

For the complete, always-current route list (including backtesting endpoints), see:
- `paper_trading_ui/backend/main.py`

## Request Schemas

New schemas introduced in `paper_trading_ui/backend/schemas.py`:

| Schema | Fields | Used by |
|--------|--------|---------|
| `AccountParamsRequest` | `strategy` (optional str), `riskPolicy` (optional str) | `PATCH /api/accounts/{name}/params` |
| `ManualTradeRequest` | `ticker`, `side` (`"buy"`\|`"sell"`), `qty` (>0), `price` (>0), `fee` (≥0, default 0) | `POST /api/accounts/{name}/trades` |
| `FeatureSignalsRequest` | `ticker` | `POST /api/features/signals` |

## Backend Boundary Notes

- Route modules under `paper_trading_ui/backend/routes/` should stay thin and delegate DB mutations to backend service helpers.
- Backend service modules now live under `paper_trading_ui/backend/services/`.
- Admin account deletion now delegates to canonical runtime data-ops (`trading.interfaces.runtime.data_ops.admin`) through `paper_trading_ui/backend/services/admin.py`.
- New UI/backend code should use canonical runtime data-ops modules (`trading.interfaces.runtime.data_ops.*`).
- Account snapshot history, account-name listing, and recent backtest-run list queries are exposed through backend service helpers instead of inline route SQL.
- Managed-account listing and latest-backtest lookup in backend account services are routed through trading repository adapters.
- Account existence and latest-snapshot lookups in backend DB/test-account services are routed through trading repository adapters.
