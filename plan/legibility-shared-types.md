# Plan: shared types for sides, holdings, trades, payloads, and small vocabulary cleanups

Status (2026-11-11): drafted. Item 1 is built on `feature/side-and-gate-action-vocabulary`, not committed.
Items 2-5 are not started. No owner decision is open.

Keep this file until the "Left to do" list is empty.

## Left to do
Check these off in the pull request that does each one; delete this file when none remain.
1. **Item 1, side and gate-action vocabulary.** Built, uncommitted. Commit, open the pull request, merge.
2. **Item 2, one holdings type.**
3. **Item 3, a `Trade` value object.**
4. **Item 4, typed payloads** (4a position analysis, 4b autonomy monitor, 4c burn-in entries).
5. **Item 5, small cleanups** (5a instrument-mode vocabulary, 5b attribute reads on records, 5c two named
   operations).

## Goal
Make the code quicker to read and review. The same trading concepts travel today as bare strings, parallel
dicts, and `dict[str, object]` rows, so each function re-derives what it is holding. Give each concept one
named type and move the repeated handling onto it.

This is a readability refactor. **No item changes behaviour**, with one exception named in item 3: stored
values, JSON payloads, run artifacts, and computed numbers stay the same. An item that cannot be done without
any other behaviour change stops and asks.

## What exists (verified in the code, 2026-11-11)
Names, not line numbers; lines move.

- **Sides and gate actions (item 1, built).** `Side` (`trading/models/orders.py`) and `RiskGateAction`
  (`trading/models/execution.py`) are `StrEnum`s. Members equal the stored text, so database rows and JSON are
  unchanged. `RiskGateDecision.action` is typed `RiskGateAction`; every `side` field is still `str`.
- **Holdings are declared four times.** `cash` + `positions` + `avg_cost` appear in `AccountState`
  (`trading/models/accounts.py`, Decimal, the replay result), `BookTradeState` (`trading/models/execution.py`,
  float, frozen), `_WorkingState` (`trading/services/execution/selection/selection.py`, float, mutable), and
  `_PortfolioState` (`backtesting/services/simulation.py`, float, mutable).
- **The fill functions take the two dicts separately.** `apply_buy` (7 positional arguments) and `apply_sell`
  (8) in `trading/domain/accounting/account.py` mutate the caller's `positions` and `avg_cost` in place and
  return the new cash (and realized P&L). Callers: `_apply_trade_to_state` in the same module,
  `_closed_trade_stats` in `backtesting/domain/metrics.py`, and `_execute_sells` / the buy phase in
  `backtesting/services/simulation.py`.
- **Float and Decimal are both in use on purpose.** `Number = TypeVar("Number", float, Decimal)` in
  `trading/domain/accounting/ledger.py` keeps each call single-typed: the live replay is Decimal, the backtest
  is float (ADR 020).
- **Trades are `dict[str, object]` rows** with keys `ticker`, `side`, `qty`, `price`, `fee`, and for the live
  path also `book_id`, `trade_time`, `note`. Producers: `_fill_events` and `_cash_events` in
  `trading/services/execution/ledger/queries.py` (returned by `list_account_trades`), and `_record_trade` in
  `backtesting/services/simulation.py` (`executed_trades`). Consumers: `compute_account_state` (through
  `normalize_trade_fields_decimal`), `_closed_trade_stats` / `summarize_backtest_performance` (through
  `normalize_trade_fields`), `backtesting/services/reporting.py`, and `build_trade_payload` in
  `apps/paper_trading_web/backend/services/accounts/data_access.py`.
- **Two tests pin the unknown-side error text**: `"Unsupported side: hold"` in
  `tests/src/trading/domain/test_accounting.py` and `"Unsupported trade side"` in
  `tests/src/backtesting/domain/test_metrics.py`.
- **Position analysis returns `list[dict[str, float | str]]`** (`compute_position_analysis` in
  `trading/services/analysis/position.py`), and its readers re-coerce with `float(position["..."])` in the same
  module and in `trading/services/analysis/queries.py`. The web backend shapes it in
  `apps/paper_trading_web/backend/services/analysis.py`.
- **`trading/services/autonomy_monitor/queries.py` returns `dict[str, Any]` throughout.** Its one consumer is
  `apps/paper_trading_web/backend/services/autonomy_monitor.py`.
- **Daily-run step details are a persisted contract.** `DagStepResult.details` is written into every run
  artifact and read back by `burn_in_status.py` and the replay job. Burn-in `entry` dicts are built in-process
  by `scan_artifacts` from those artifacts.

## Work items
One pull request per item, in order. Each passes the gate on its own.

### 1. Side and gate-action vocabulary (built, uncommitted)
- Done: the two enums, literal replacements in 23 source files, and `tests/src/trading/models/test_vocabulary.py`.
- Left untouched on purpose: strategy **signals** (`"buy"` / `"sell"` / `"hold"` in
  `trading/domain/strategies/signals/technical.py`, and the signal comparisons in `selection.py` and
  `simulation.py`). A signal is not an order side. See "Out of scope".
- No `signed_amount` helper: a settlement-ticker buy is a deposit (positive) in `ledger/mutations.py`, while a
  trade buy is a cash outflow (negative) in `submission.py`. One helper would hide that.

### 2. One holdings type
Add `Holdings` in a new module `trading/domain/accounting/holdings.py` (domain, not models: it has behaviour).

- Shape: a mutable `@dataclass` generic over `Number` with `cash`, `positions: dict[str, Number]`,
  `avg_cost: dict[str, Number]`, and `realized_pnl`.
- Methods: `buy(ticker, qty, price, fee)` and `sell(ticker, qty, price, fee)`, which hold the logic now in
  `apply_buy` / `apply_sell` (same checks, same error text, same use of `buy_position_delta` /
  `sell_position_delta`) and update `cash` and `realized_pnl` on the object. `open_positions()` holds the logic
  now in `_compact_positions`.
- A missing ticker must still read as zero of the caller's number type. The three callers use
  `defaultdict(float)` / `defaultdict(Decimal)` today; keep that inside `Holdings` (a constructor such as
  `Holdings.starting_with(cash)` that builds both dicts from `type(cash)`).
- Move the callers in the same pull request and delete `apply_buy`, `apply_sell`, and `_compact_positions`. No
  forwarding shims (architecture conventions, Import and Facade Rules).
  - `compute_account_state` replays into a `Holdings[Decimal]` and still returns `AccountState`.
  - `_closed_trade_stats` replays into a `Holdings[float]`.
  - `_PortfolioState` keeps `trade_count` and `executed_trades` and holds a `Holdings[float]` for the rest.
  - `_WorkingState` is replaced by `Holdings[float]` if selection needs nothing else from it.
    **Unverified:** selection pops closed tickers out of both dicts directly and never calls `apply_sell`;
    confirm `Holdings.sell` gives the same cash and positions there before switching, otherwise leave
    `_WorkingState` and say so in the summary.
- Stays as it is: `AccountState` and `BookTradeState` (passive models, read in many places), the
  `TradePreparationStateLike` protocol, and both valuation policies in `trading/domain/metrics/portfolio_math.py`
  (its docstring says not to converge them). Valuation methods on `Holdings` are not part of this item.
- Tests: new `tests/src/trading/domain/test_holdings.py` for buy, sell, oversell, re-averaging, and
  `open_positions`, in both float and Decimal. Existing accounting, backtest-metrics, and simulation tests must
  pass with only call-shape edits; an expected number that changes is a stop.

### 3. A `Trade` value object
Add a frozen `Trade` dataclass, generic over `Number`, with `ticker`, `side`, `qty`, `price`, `fee`, and the
optional display fields `book_id`, `trade_time`, `note`.

- It lives in a new module `trading/models/trades.py` (owner decision, 2026-11-11). Move the `Number` type
  variable there, with its comment, and have `trading/domain/accounting/ledger.py` and every other user import
  it from `trading.models.trades`. Do not leave a re-export behind in `ledger.py`. Add the module to
  `docs/maps/trading-package-map.md` if the docs check asks for it.

- `Trade.from_mapping(row)` replaces `normalize_trade_fields` and `normalize_trade_fields_decimal`: ticker
  upper-cased, side lower-cased, missing numerics read as zero. Two constructors or a number-type argument,
  whichever keeps mypy single-typed.
- A `notional` property (`qty * price`) replaces the inline products in the replay code this item touches. Do
  not chase every `qty * price` in the repository.
- Producers return `Trade`: `_fill_events`, `_cash_events`, `list_account_trades` (Decimal), and
  `_record_trade` / `executed_trades` (float). `backtesting/services/reporting.py` converts its stored rows with
  `from_mapping`.
- Consumers take `Trade`: `compute_account_state`, `_closed_trade_stats`, `summarize_backtest_performance`.
- `build_trade_payload` reads attributes and must emit the same JSON keys and values. Add or extend a test that
  pins that payload before changing it.
- `side` is typed `Side` (owner decision, 2026-11-11). `from_mapping` parses it, so an unknown side raises
  `ValueError` there, naming the bad value, before any replay runs. This is the one sanctioned behaviour change
  in the plan: the two replay loops lose their own unknown-side branches, and the two tests that pin
  "Unsupported side: hold" and "Unsupported trade side" are updated to the new text.
- Tests: `from_mapping` in float and Decimal, including a missing numeric, mixed-case input, and an unknown
  side; the existing replay and metrics tests updated to build `Trade`s.

### 4. Typed payloads
Three independent parts; each can be its own commit.

- **4a. Position analysis.** Add a frozen `PositionAnalysis` dataclass (`trading/models/portfolio.py`) with the
  nine fields `compute_position_analysis` builds today. `compute_position_analysis`, `generate_improvement_notes`,
  and `fetch_account_analysis` use attributes, which removes the `float(position["..."])` re-coercions.
  `apps/paper_trading_web/backend/services/analysis.py` reads attributes and emits the same JSON.
  **Unverified:** whether anything else reads `top_winners` / `top_losers` as dicts (CLI or reporting); search
  before changing the return type.
- **4b. Autonomy monitor.** Replace the `dict[str, Any]` returns in
  `trading/services/autonomy_monitor/queries.py` with frozen dataclasses in a `trading/models/` module, one per
  payload (account summary, book row, rotation row, risk summary). The web backend service shapes them.
  **Unverified:** the exact key set the backend and frontend read; list it from
  `apps/paper_trading_web/backend/services/autonomy_monitor.py` and its tests first, and keep the HTTP response
  byte-for-byte the same.
- **4c. Burn-in entries.** Give the `entry` dicts built by `scan_artifacts` in `burn_in_status.py` a `TypedDict`
  (some keys are optional, so `total=False` or `NotRequired`). Type annotations only; no runtime change, and the
  JSON the job writes is unchanged.
- Not in this item: `DagStepResult.details`. It is the persisted run-artifact shape and its readers parse
  artifacts from disk, so the `isinstance` checks there are doing real work (owner decision, 2026-11-11).

### 5. Small cleanups
Three independent parts, each its own commit. All behaviour-preserving.

- **5a. Instrument-mode vocabulary.** Add an `InstrumentMode` `StrEnum` (`EQUITY = "equity"`, `LEAPS = "leaps"`)
  in `trading/models/books.py`, the same pattern as `Side` in item 1. Build `INSTRUMENT_MODES` and
  `DEFAULT_INSTRUMENT_MODE` from it so existing importers keep working, and replace the bare comparisons
  (`instrument_mode == "leaps"` in `services/execution/selection/selection.py`,
  `domain/auto_trading/sizing.py`, `backtesting/domain/risk_warnings.py`, `services/reporting/account.py`) and
  the re-listed values in `interfaces/cli/commands/options.py` and
  `apps/paper_trading_web/backend/account_options.py`. Leave `instrument_mode: str` field types and the
  pydantic schema default as they are. Extend `test_vocabulary.py` to pin the two values.
- **5b. Attribute reads on typed records.** Where a parameter is annotated `AccountRecord` or `BookRecord`,
  replace dict-style reads with attributes: `row_expect_str(account, "benchmark_ticker")` becomes
  `account.benchmark_ticker`, `row_expect_int(account, "id")` becomes `account.id`. Known sites:
  `services/evaluation/evidence.py`, `services/analysis/portfolio.py`, `services/analysis/queries.py`,
  `services/reporting/account.py`.
  - `row_expect_float(account, "initial_cash")` converts a Decimal to float; keep that conversion explicit
    (`float(account.initial_cash)`), do not drop it.
  - **Unverified:** whether tests or callers pass a plain dict where the annotation says a record. If one
    does, fix the test to build the record; if a runtime caller does, leave that site and write a question.
  - Not in this part: `domain/auto_trading/options.py`, whose parameter is `AccountPolicyInput`, not a record;
    and removing the `Mapping` base from `AccountRecord` / `BookRecord`. Report in the summary how many
    dict-style reads of those two records remain, so the owner can decide on the base class later.
- **5c. Two named operations.**
  - Book equity total: `sum(float(book.current_equity) for book in books)` appears in
    `services/execution/risk.py`, `services/execution/equity_reconciliation.py`, and
    `services/autonomy_monitor/queries.py`. Add one function and use it in all three. It needs no I/O, so it
    belongs in `trading/domain/`; pick the module by the placement rules in the architecture conventions and
    name it without a transport or persistence verb. Keep the float result.
  - `_build_risk_violations` in `services/analysis/daily_report.py` counts actions in three passes; use one
    `collections.Counter` over `decision.action` and read the three counts from it.

## Constraints
- Read `docs/architecture/architecture-conventions.md` in full before editing `src/trading/`. `models/` is
  passive and imports nothing from `domain`; `domain` is side-effect free.
- Items 2 and 3 touch accounting math shared by the live path and the backtester. Per the `implement-plan`
  skill, say so in the summary so the pull request stays a draft for the owner's review.
- A file move and a behaviour change are separate steps. In item 3, move `Number` in its own commit, before
  the commit that changes the unknown-side handling.
- No comments that narrate the change. Rationale goes in commit messages.
- Nothing here is strategy-specific; all of it is intentionally public. Do not touch `local/` or strategy
  parameters.
- Run `python -m scripts.fix_checks`, then `python -m scripts.run_checks pr --base origin/develop`.
- **Environment (seen 2026-11-11 on the dev PC):** the `.venv` editable install resolved to a different
  checkout, so `pytest` failed on import until `PYTHONPATH` pointed at this checkout's `src` and `apps`. If
  imports fail the same way, report it; do not reinstall the environment unasked.

## Suggested order
1, then 2, then 3, then 4. Item 3 reads more simply once `Holdings` exists (the replay loop becomes
`holdings.buy(...)` over `Trade`s). Items 4 and 5 do not depend on 2 or 3 and can go in any order; 5 is the
smallest and a good first hand-off.

## Decisions (owner, 2026-11-11)
- `Trade.side` is typed `Side`; an unknown side fails at parse (item 3).
- `Trade` and the `Number` type variable live in `trading/models/trades.py` (item 3).
- `DagStepResult.details` stays `dict[str, object]` (item 4).

## Held back (owner, 2026-11-11)
Considered and deliberately not planned here.
- A `Signal` vocabulary for `"buy"` / `"sell"` / `"hold"`. It touches the tracked signal functions, so it
  needs a public or private classification first (`AGENTS.md`, Core rules).
- Typing the remaining `side: str` fields as `Side`. Each needs parsing where its rows are read, which is a
  behaviour change per site; revisit after item 3 shows the pattern.
- The `float(...)` conversions of Decimal money fields (about 50 sites). That is where the Decimal-to-float
  boundary sits, which is a design decision, not cleanup.

## Out of scope
- Generic list helpers (`group_by`, `count_where`). The grouping, counting, and index-by-key idioms are few and
  already read clearly.
- Converging the float and Decimal paths, or the lenient and strict valuation policies.
- Any schema, broker, or runtime-job change.

## Developer verification (fill in when the work ships)
- Item 1: `git grep -nE '"(buy|sell)"' src` returns only signal sites, docstrings, field comments, and the enum
  definitions; `python -m scripts.checks.run_suite all --no-cov` passes (4326 passed, 10 skipped on 2026-11-11).
- Items 2-5: to be filled in.
