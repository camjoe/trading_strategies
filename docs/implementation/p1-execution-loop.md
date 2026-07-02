# Implementation Guide — P1: Close the execution loop (keystone)

Type: implementation
Status: Ready (large; multi-commit; mixed light/strong steps)
Initiative: P1 (Close the execution loop)
Estimate: L
Created: 2026-07-01
Last Reviewed: 2026-07-01
Related: [Plan](../plan.md), [Decisions](../decisions.md#d1), [Overview](../overview.md),
[Implementation README](README.md)

> Follows the [template](p2-evaluation-contract-tests.md) and the [operating model + execution
> protocol](README.md). P1 has real logic, so steps are marked **[light]** (mechanical, safe to hand
> to a light model) or **[strong]** (design/logic — strong model or careful human review). Do the
> steps in order; each is its own green commit.

## 1. Objective

Make the live/paper trader actually run the active strategy's **signal function** to decide trades,
instead of the legacy random/style-biased placeholder. Trade **only on real signals**, with a
**per-run max cap and no forced minimum** ([D1](../decisions.md#d1)). Backtest and live share **one**
signal-evaluation entry so backtest evidence reflects live behavior.

### Scope note (honest bound)
On the **current** schema, strategy knobs come from the code registry's `default_params`. The
"parameters as data" lever (account/strategy-row knobs) arrives with **P3**; P1 only needs backtest↔
live **parity** on one `evaluate_signal(strategy, history, params, feature_history)`.

### Definition of Done
- [ ] Live/paper selection is driven by the active strategy's signal per candidate ticker.
- [ ] No forced-minimum trades; a per-run **max cap** bounds trade count.
- [ ] Backtest and live both evaluate signals through one shared function with the same params.
- [ ] Rotating a unit/account to a strategy changes what the trader actually does.
- [ ] `python -m scripts.run_checks --profile ci` green.
- [ ] Plan P1 status updated.

## 2. Preconditions
- Branch `features/p1-execution-loop` off the latest `develop`.
- [D1](../decisions.md#d1) is resolved (this guide encodes it). `./.venv` exists.

## 3. Background (current code)
- Signals run **only in backtest**: `resolve_signal(strategy, history, feature_history)` →
  `spec.signal_fn(history, spec.default_params, feature_history)` in
  `src/trading/domain/strategy_signals.py`, called from
  `src/trading/backtesting/services/execution_service.py`.
- Live selection: `run_for_account` (runtime) → `run_for_account_impl`
  (`src/trading/services/auto_trading/execution.py`) loops `target = randint(min_trades, max_trades)`
  and calls `prepare_trade_selection` → `prepare_buy_trade`/`prepare_sell_trade` →
  `auto_trading_policy.choose_buy_ticker`/`choose_side` (random / return-heuristic, style bias). **No
  `signal_fn`, no history** (only a `prices` dict is passed).
- Backtest model to mirror (`execution_service.py`): per ticker, `history = close.loc[:date, ticker]`
  → `resolve_signal` → act on buy/sell.

## 4. Guardrails
- Venv interpreter; respect layering; never set `live_trading_enabled`; never construct brokers inline.
- Behavior change is intended, but **only** the selection/eval path — do not touch broker submission,
  risk gates, reconciliation, or accounting.
- If a step needs a decision not covered by D1 → **stop and report** (do not improvise).

## 5. Steps (ordered; each a green commit)

### Step 1 — Shared signal evaluation  **[light]**
- `src/trading/domain/strategy_signals.py`: add
  `evaluate_signal(strategy_name, history, params, feature_history=None) -> str` that resolves the spec
  and returns `spec.signal_fn(history, params, feature_history)`. Make `resolve_signal` delegate:
  `return evaluate_signal(strategy_name, history, spec.default_params, feature_history)`.
- Test: `evaluate_signal` with explicit params overrides `default_params` (e.g. a trend strategy with
  a tiny `fast_window` flips the signal).
- Check: `run_suite src/trading/domain` (or the strategy-signals tests) + backtesting suite still green.

### Step 2 — Param resolution helper  **[light]**
- Add `resolve_strategy_params(account, strategy_name) -> dict` (in `auto_trading/execution.py` or a
  small `domain` helper). **For now it returns the strategy's `default_params`** (the account/data
  layer is P3). Keep it a single seam so P3 can extend it.
- Test: returns the registry default_params for a known strategy.

### Step 3 — Thread per-ticker history through selection  **[strong]**
- Add a `histories: dict[str, pd.Series]` parameter alongside the existing `prices` dict, threaded:
  `runtime.run_for_account` → `run_for_account_impl` → `prepare_trade_selection`. (Mirror how `prices`
  already flows; do **not** fetch inside domain selection.)
- Selection reads `history = histories.get(ticker)`; if missing/too short for the strategy's window →
  treat as `hold` (skip). Keep signatures typed; `mypy` clean.
- Check: layer + mypy clean; existing tests compile (they will need updating in Step 7).

### Step 4 — Signal-driven selection (core)  **[strong]**
- Replace the `target = randint(min_trades, max_trades)` loop and the random/heuristic
  `choose_buy_ticker`/`choose_side` with the backtest-mirroring algorithm in `run_for_account_impl`:
  - compute `strategy = active strategy`, `params = resolve_strategy_params(...)`, `held = qty>=1`.
  - for each ticker in the universe: `sig = evaluate_signal(strategy, histories.get(ticker), params,
    feature_history_for(ticker))`; collect **buy** candidates (sig=="buy", not held) and **sell**
    candidates (sig=="sell", held). Keep the existing `forced_sell` risk-stop path.
  - size via the existing `choose_buy_qty` / sell sizing and the existing risk gates.
  - submit candidates **up to `max_trades`** (the cap); **no forced minimum** — if nothing signals,
    submit nothing.
- `min_trades` becomes unused for the floor (leave the param but ignore it, or remove; note for config
  cleanup). `choose_buy_ticker`/`choose_sell_ticker`/`choose_side` become dead → remove (cleanup).
- **`learning_enabled` no longer drives selection** — it becomes a no-op here; note it for P10, do not
  try to preserve its old meaning.
- Check: new/updated selection unit tests (Step 7) green.

### Step 5 — Runtime job supplies histories  **[strong]**
- Find the caller(s): `grep -rn "run_for_account(" src` (the daily paper-trading auto-trades job).
- Where it builds `prices`, also build `histories` via the injected `MarketDataProvider.fetch_close_series(ticker, period)`
  (fixed lookback ~1y per D1; cache per run). Pass `histories` into `run_for_account`.
- Check: the job's tests (`run_suite src/trading/interfaces/runtime/jobs/daily`) green with a stubbed provider.

### Step 6 — Sleeve path parity  **[strong]**
- `src/trading/services/sleeves/execution.py` `generate_sleeve_trade_intents` shares
  `prepare_trade_selection`, so it inherits the signal-driven path — thread `histories` through the same
  way and confirm sleeve intents are signal-driven (not random).
- Check: `run_suite src/trading/services/auto_trading src/trading/services/sleeves` green.

### Step 7 — Tests  **[mixed]**
- Selection: signals-only (buy on buy-signal, sell on sell-signal), **no forced minimum** (all-hold →
  zero trades), **max cap** honored, stale/missing history → hold. Use a stub `evaluate_signal` /
  injected `histories`.
- Update `tests/src/trading/services/auto_trading/*` and `tests/src/trading/services/sleeves/*` that
  assumed random selection / min-trades.
- Backtest parity: assert backtest still uses `evaluate_signal` (via `resolve_signal`) with default params.

### Step 8 — Backtest parity check  **[light]**
- Confirm `execution_service.py` path is unchanged in behavior (it uses `resolve_signal`, which now
  delegates to `evaluate_signal` with `default_params`). Add/keep a test asserting identical signals.

## 6. Validation
```
.venv\Scripts\python.exe -m scripts.checks.run_suite src/trading/services/auto_trading src/trading/services/sleeves src/trading/domain src/trading/backtesting --no-cov
.venv\Scripts\python.exe -m scripts.checks.layer_check
.venv\Scripts\python.exe -m scripts.checks.mypy_check
.venv\Scripts\python.exe -m scripts.run_checks --profile ci      # final
```

## 7. Failure handling
- History wiring balloons beyond the `histories`-dict seam → stop and report; do not fetch inside domain.
- A test encodes old random/min-trades behavior as intended → update it to the new policy (this is an
  intended behavior change), but if unsure whether a behavior is intended, **stop and ask**.
- Any check red → do not commit.

## 8. Handoff / PR
- Push `features/p1-execution-loop`; open a PR summarizing the phases + validation, or hand back.
- Update [plan.md](../plan.md): P1 status; check off 3-E1 (and note 3-E2 as parity-only, data-param
  layer deferred to P3).

## 9. Out of scope
- Parameters-as-data (account/strategy-row knobs) — P3/P6.
- Any DB schema change — P3.
- Convergence of account/sleeve submission — P4.

## 10. Final report (per `AGENTS.md`)
- **Developer verification:** run a paper account through the daily job; confirm trades match the
  active strategy's signals (not random), obey the cap, and are empty when nothing signals.
- **Validation run:** §6 commands + results.
- **Cleanup notes:** removed `choose_buy_ticker`/`choose_sell_ticker`/`choose_side`; `min_trades`
  floor + `learning_enabled` selection role retired (flag for P10).
