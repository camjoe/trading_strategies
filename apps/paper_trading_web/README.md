# Paper Trading Web UI

Web dashboard and API for viewing paper trading accounts, snapshots, trades, and logs.

## Purpose

Provide a local dashboard and API for paper-trading operations, including:

- **Account visibility** — live summary cards and per-account detail (summary, analysis, positions, trades, snapshots, config, backtest metrics, and live benchmark overlays). The Summary section includes a compact posture/snapshot block for latest snapshot timing, snapshot deltas, cash, market value, and latest realized/unrealized P&L.
- **Account workspace** — a focused one-account-at-a-time workspace with account switching/search, dedicated internal detail tabs, and trade history kept inside the selected account instead of a separate trade tab.
- **Alt Strategies tab** — health status of the three alt-strategy feature providers (Policy, News, Social) and on-demand signal lookup for any ticker. Each signal result includes a feature breakdown table, per-feature descriptions, and a plain-English interpretation of the current feature values.
- **Account parameter editing** — a dedicated Config section for reviewing and updating core, options, and rotation fields per managed account, including `rotationOverlayWatchlist` for regime overlays.
- **Compare view** — side-by-side performance table for all accounts with strategy-filter dropdown, live benchmark return, and live alpha columns.
- **Snapshots and operational logs** — snapshot actions stay in the account workspace, while operational logs now live under **Admin > Artifacts & Logs**.
- **Admin operations visibility** — runtime job health plus recent scheduled refresh, daily snapshot, database-backup, promotion-review visibility, CSV database exports, and operational log browsing all live inside the Admin tab, grouped into focused Admin sub-sections instead of extra top-level tabs.

## Environment Setup

Copy the example env files once before first run:

```sh
cp apps/paper_trading_web/backend/.env.example apps/paper_trading_web/backend/.env
cp apps/paper_trading_web/frontend/.env.example apps/paper_trading_web/frontend/.env
```

Backend env supports `CORS_ORIGINS` and `LOGS_DIR`. Frontend env supports `VITE_API_BASE` (default `http://127.0.0.1:8000`).

## Quick Start

The fastest way to start both services:

```sh
python -m scripts.launch_ui
```

This keeps both attached to your terminal. Press `Ctrl+C` to stop both. Defaults: backend `http://127.0.0.1:8000`, frontend `http://127.0.0.1:5173`.

## Manual Startup

Backend:

```sh
uvicorn paper_trading_web.backend.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```sh
cd apps/paper_trading_web/frontend
npm install
npm run dev
```

## Workflows

1. Start both services with `python -m scripts.launch_ui` for day-to-day usage.
2. Use manual startup commands when working on backend or frontend in isolation.
3. Update this README whenever API routes or UI operational flows change.

## Core API Routes

### Accounts

- `GET /api/accounts` — list visible accounts (`managed` and `local`).
- `GET /api/accounts/compare` — comparison payload for all accounts (used by the Compare tab). Includes live benchmark summary fields such as `liveBenchmarkReturnPct` and `liveAlphaPct` when enough snapshots exist.
- `GET /api/accounts/{account_name}` — full detail: summary, snapshots, trades, latest backtest, latest backtest metrics, and `liveBenchmarkOverlay`. Account summaries include `accountKind`, `brokerType`, and rotation settings such as `rotationOverlayMode`, thresholds, and `rotationOverlayWatchlist`.
- `PATCH /api/accounts/{account_name}/params` — update mutable account config and rotation fields. All fields are optional; only supplied (non-`null`) fields are applied. Body: `AccountParamsRequest`.

### Analysis

- `GET /api/accounts/{account_name}/analysis` — per-account analysis payload assembled from the canonical trading analysis service.

### Admin

- `POST /api/admin/accounts/create` — create an account. Body: `AdminCreateAccountRequest`. `accountKind` defaults to `managed`; use `local` for locally managed strategy-testing accounts. If `rotationOverlayWatchlist` is omitted, the new account starts with default tickers seeded from `src/infrastructure/config/trade_universe.txt`. That seed is persisted in DB schema/defaults, so later updates to `src/infrastructure/config/trade_universe.txt` require an explicit DB update or migration to affect already-migrated databases.
- `POST /api/admin/accounts/delete` — delete a managed account and its dependent records. Body: `AdminDeleteAccountRequest`.
- `GET /api/admin/operations/overview` — summarize scheduled job health and recent refresh/snapshot/backup artifacts discovered under `local/`.
- `GET /api/admin/promotion/overview?accountName=...&strategyName=&limit=5` — show the current computed promotion assessment plus recent persisted review history for one managed account.

### Alt-Strategy Feature Providers

- `GET /api/features/status` — probe all three alt-strategy providers (Policy, News, Social) and return availability + key scores. Each provider entry also includes `description`, `data_sources`, `feature_descriptions` (per-feature label and threshold info), and `signal_logic`.
- `POST /api/features/signals` — run all three signal functions for a ticker. Body: `FeatureSignalsRequest` (`ticker`). Returns per-strategy `signal`, `available`, `features`, `interpretation` (human-readable summary of current feature values), `feature_descriptions`, and `signal_logic`.

### Logs

- `GET /api/logs/files` — list available log files.
- `GET /api/logs/{file_name}?limit=400&contains=error` — tail/filter a log file.

### Actions

- `POST /api/actions/snapshot/{account_name}` — take a snapshot for one account.
- `POST /api/actions/snapshot-all` — snapshot all managed accounts.

### Backtests

- `GET /api/backtests/runs` — recent persisted backtest runs for dashboard selection.
- `GET /api/backtests/latest/{account_name}` — latest persisted backtest summary for an account.
- `GET /api/backtests/runs/{run_id}` — full persisted backtest report payload for a specific run.
- `POST /api/backtests/preflight` — validate backtest configuration and return warnings before execution.
- `POST /api/backtests/run` — run a backtest and return persisted summary metrics.
- `POST /api/backtests/walk-forward` — run a walk-forward backtest and return aggregate window metrics plus persisted `runIds`.

### Health

- `GET /health`

For the complete, always-current route list (including backtesting endpoints), see `apps/paper_trading_web/backend/main.py`.

## Request Schemas

Key account/admin and feature schemas in `apps/paper_trading_web/backend/schemas/`:

| Schema | Fields | Used by |
|--------|--------|---------|
| `AdminCreateAccountRequest` | Account creation payload with core fields plus `accountKind` and rotation settings. `accountKind` defaults to `managed`; use `local` for local strategy-testing accounts. Includes `rotationOverlayMode`, `rotationOverlayMinTickers`, `rotationOverlayConfidenceThreshold`, and optional `rotationOverlayWatchlist`. Omitted watchlist values fall back to the seeded `src/infrastructure/config/trade_universe.txt` default (see Admin route note above for migration behavior). | `POST /api/admin/accounts/create` |
| `AdminDeleteAccountRequest` | `accountName`, `confirm` | `POST /api/admin/accounts/delete` |
| `BacktestRunRequest` | `account`, date/window selection, optional universe-history inputs, slippage/fee, optional `runName`, and `allowApproximateLeaps` | `POST /api/backtests/run` |
| `BacktestPreflightRequest` | Same account/date/universe inputs as a run request, without execution fields | `POST /api/backtests/preflight` |
| `WalkForwardRunRequest` | Backtest request fields plus `testMonths`, `stepMonths`, slippage/fee, and optional `runNamePrefix` | `POST /api/backtests/walk-forward` |
| `AccountParamsRequest` | Optional mutable account fields — only supplied (non-`null`) fields are applied. **Core:** `strategy`, `accountKind`, `descriptiveName`, `riskPolicy`, `stopLossPct`, `takeProfitPct`, `instrumentMode`, `learningEnabled`. **Goals:** `goalMinReturnPct`, `goalMaxReturnPct`, `goalPeriod`. **Options:** `optionType`, `optionMinDte`, `optionMaxDte`, `optionStrikeOffsetPct`, `targetDeltaMin`, `targetDeltaMax`, `ivRankMin`, `ivRankMax`, `maxPremiumPerTrade`, `maxContractsPerTrade`, `rollDteThreshold`, `profitTakePct`, `maxLossPct`. **Rotation:** `rotationEnabled`, `rotationMode`, `rotationOptimalityMode`, `rotationIntervalDays`, `rotationIntervalMinutes`, `rotationLookbackDays`, `rotationSchedule`, `rotationRegimeStrategyRiskOn`, `rotationRegimeStrategyNeutral`, `rotationRegimeStrategyRiskOff`, `rotationOverlayMode`, `rotationOverlayMinTickers`, `rotationOverlayConfidenceThreshold`, `rotationOverlayWatchlist`, `rotationActiveIndex`, `rotationLastAt`, `rotationActiveStrategy`. | `PATCH /api/accounts/{name}/params` |
| `FeatureSignalsRequest` | `ticker` | `POST /api/features/signals` |

## Backend Boundary Notes

- Route modules under `apps/paper_trading_web/backend/routes/` should stay thin and delegate DB mutations to backend service helpers.
- Backend service modules now live under `apps/paper_trading_web/backend/services/`.
- Admin account creation is handled by `create_account_with_rotation()` in `apps/paper_trading_web/backend/services/admin.py`. This function absorbs `AccountAlreadyExistsError` from the trading domain and re-raises it as `ValueError`; HTTP-layer translation (400 vs 409 etc.) stays in the route handler, not the service.
- Admin account deletion previews cascade impact, then delegates to the shared deletion service (`trading.services.accounts.delete_account`, cascade-backed) through `apps/paper_trading_web/backend/services/admin.py`.
- New UI/backend code should use canonical runtime data-ops modules (`trading.interfaces.runtime.data_ops.*`).
- Account snapshot history and recent backtest-run list queries are exposed through backend service helpers instead of inline route SQL. Account-name and account-row access now use canonical trading service names directly (`fetch_accounts`, `list_names`) — local wrapper aliases were removed in the boundary refactor.
- Managed-account listing and latest-backtest lookup in backend account services are routed through trading repository adapters.
- Account existence and latest-snapshot lookups in backend DB services are routed through trading repository adapters.

## Frontend Boundary Notes

- Keep feature entrypoints thin: `apps/paper_trading_web/frontend/src/features/accounts.ts` and `apps/paper_trading_web/frontend/src/features/admin.ts` are wrapper surfaces, while feature-specific orchestration lives under `apps/paper_trading_web/frontend/src/features/accounts/` and `apps/paper_trading_web/frontend/src/features/admin/`.
- Keep account-detail rendering split by concern under `apps/paper_trading_web/frontend/src/components/account-detail/` so section rendering changes do not accumulate back into one oversized `components/detail.ts`.
