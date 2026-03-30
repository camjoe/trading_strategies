# API Reference — Work In Progress

Content staged here pending registry/generation pipeline support.
Once the pipeline is extended, these sections should be generated and removed from this file.

## Query Parameters

Source: route handlers in `paper_trading_ui/backend/routes/`.

| Endpoint | Parameter | Details |
| --- | --- | --- |
| GET /api/logs/{file_name} | limit | int, default 400, min 10, max 4000 — number of lines to return. |
| GET /api/logs/{file_name} | contains | string or null — case-insensitive substring filter applied before line limit is sliced. |
| GET /api/backtests/runs | limit | int, default 50, min 1, max 500 — max runs returned. |
| GET /api/admin/exports/csv/preview | exportName | string (required, min 1) — export set name to preview. |
| GET /api/admin/exports/csv/preview | fileName | string (required, min 1) — file within the export set to preview. |
| GET /api/admin/exports/csv/preview | limit | int, default 200, min 1, max 2000 — max rows returned in the preview. |

## API: Request Body Models

Source: Extractable from `paper_trading_ui/backend/schemas.py`.

### POST /api/admin/accounts/create (AdminCreateAccountRequest)

| Field | Type / Default | Notes |
|---|---|---|
| name | string (required) | Unique account identifier. |
| strategy | string (required) | Strategy key (e.g. trend, mean_reversion, ma_crossover). |
| initialCash | float (required, > 0) | Starting cash balance. |
| benchmarkTicker | string, default SPY | Benchmark for alpha calculations. |
| descriptiveName | string \| null | Optional human-readable display name. |
| goalPeriod | string, default monthly | One of: monthly, weekly, quarterly, yearly. |
| goalMinReturnPct / goalMaxReturnPct | float \| null | Optional return range targets for the goal period. |
| learningEnabled | bool, default false | Enable adaptive learning mode. |
| riskPolicy | string, default none | One of: none, fixed_stop, take_profit, stop_and_target. |
| stopLossPct / takeProfitPct / profitTakePct / maxLossPct | float \| null | Risk control thresholds (used depending on riskPolicy). |
| instrumentMode | string, default equity | One of: equity, leaps. |
| optionType | string \| null | One of: call, put, both (only relevant for leaps mode). |
| optionStrikeOffsetPct | float \| null | Strike offset as percentage from current price. |
| optionMinDte / optionMaxDte | int \| null | DTE range for options selection. |
| targetDeltaMin / targetDeltaMax | float \| null, 0–1 | Delta range for target options. |
| ivRankMin / ivRankMax | float \| null, 0–100 | IV rank filter range. |
| maxPremiumPerTrade | float \| null | Cap on premium paid per options trade. |
| maxContractsPerTrade | int \| null | Max contract count per trade. |
| rollDteThreshold | int \| null | DTE at which to roll an existing options position. |
| rotationEnabled | bool, default false | Enable strategy rotation for this account. |
| rotationMode | string, default time | One of: time, optimal. |
| rotationOptimalityMode | string, default previous_period_best | One of: previous_period_best, average_return. |
| rotationIntervalDays | int \| null | Days between time-based rotations. |
| rotationLookbackDays | int \| null | Lookback window (days) for optimal-mode evaluation. |
| rotationSchedule | string[] \| null | Ordered list of strategy keys to rotate through. |
| rotationActiveIndex | int, default 0 | Current position in the rotation schedule. |
| rotationActiveStrategy | string \| null | Explicitly set active strategy (overrides index lookup). |
| rotationLastAt | string \| null | ISO datetime of last rotation event. |

### POST /api/admin/accounts/delete (AdminDeleteAccountRequest)

| Field | Type / Default | Notes |
|---|---|---|
| accountName | string (required) | Name of the account to delete. |
| confirm | bool, default false | Must be true or the request is rejected with 400. |

### POST /api/backtests/run (BacktestRunRequest)

| Field | Type / Default | Notes |
|---|---|---|
| account | string (required) | Account name to run against. |
| tickersFile | string, default trading/config/trade_universe.txt | Ticker universe file path. |
| universeHistoryDir | string \| null | Optional point-in-time universe history directory. |
| start / end | string \| null | Optional ISO date boundaries. |
| lookbackMonths | int \| null, > 0 | Optional lookback window if dates are omitted. |
| slippageBps | float, default 5.0 | Per-trade slippage in basis points. |
| fee | float, default 0.0 | Flat per-trade fee. |
| runName | string \| null | Optional custom run name. |
| allowApproximateLeaps | bool, default false | Allow fallback approximation for LEAP pricing if exact data is missing. |

### POST /api/backtests/preflight (BacktestPreflightRequest)

| Field | Type / Default | Notes |
|---|---|---|
| account | string (required) | Account name to validate. |
| tickersFile | string, default trading/config/trade_universe.txt | Ticker universe file path. |
| universeHistoryDir | string \| null | Optional point-in-time universe history directory. |
| start / end | string \| null | Optional ISO date boundaries. |
| lookbackMonths | int \| null, > 0 | Optional lookback window. |
| allowApproximateLeaps | bool, default false | Same fallback toggle used by run endpoints. |

### POST /api/backtests/walk-forward (WalkForwardRunRequest)

| Field | Type / Default | Notes |
|---|---|---|
| account | string (required) | Account name to run against. |
| tickersFile | string, default trading/config/trade_universe.txt | Ticker universe file path. |
| universeHistoryDir | string \| null | Optional point-in-time universe history directory. |
| start / end | string \| null | Optional ISO date boundaries. |
| lookbackMonths | int \| null, > 0 | Training lookback window. |
| testMonths | int, default 1, > 0 | Length of each test window. |
| stepMonths | int, default 1, > 0 | How far to roll forward between windows. |
| slippageBps | float, default 5.0 | Per-trade slippage in basis points. |
| fee | float, default 0.0 | Flat per-trade fee. |
| runNamePrefix | string \| null | Optional naming prefix for generated window runs. |
| allowApproximateLeaps | bool, default false | Allow LEAP approximation fallback. |

