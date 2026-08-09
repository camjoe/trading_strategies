# ADR: Shared financial math lives in trading/domain

Type: adr
Status: Proposed
Created: 2026-08-09
Last Reviewed: 2026-08-09
Purpose: Records where arithmetic used by both the live runtime and the backtester belongs, so the same quantity stops being computed two ways in two places.
Related: [architecture-conventions.md](../architecture/architecture-conventions.md), [016-optimizer-experiments-as-research-evidence.md](016-optimizer-experiments-as-research-evidence.md)

## Context

`src/backtesting/` is a bounded context beside `src/trading/`, justified by owning seven
tables nothing else writes. Neither package may reach into the other's repositories;
reads cross at services, and `trading.domain`, `trading.models`, and `trading.persistence`
are shared lower layers that `backtesting` imports as layering rather than crossing.
`layer_check` enforces both directions.

What was never stated is where a *calculation* used by both sides belongs. Absent a rule,
each context grew its own copy. An audit of `src/backtesting/domain/` in August 2026 found
five instances:

1. **The account ledger, twice.** `trading/domain/accounting.py` `_apply_buy`/`_apply_sell`
   and `backtesting/domain/simulation_math.py` `update_on_buy`/`update_on_sell` carry
   identical cost-basis and realized-P&L arithmetic. They diverge in three places: the live
   version rejects fractional quantities (`_require_whole_units`), the backtest version does
   not; the live version drops a closed position's key via `_compact_positions`, the backtest
   version zeroes it in place; the live version documents that a $0 sell is valid for expired
   options, the backtest version allows it silently.
2. **Sharpe, twice.** `backtesting/domain/metrics.py::sharpe_ratio` over pandas, and
   `trading/domain/daily_metrics.py::_trailing_risk_adjusted_score` in pure Python. The
   latter's docstring asserts it matches the former.
3. **Total return, four ways.** `backtesting.domain.metrics.total_return_pct` (raises on zero),
   `trading.domain.returns.safe_return_pct` (returns `None`),
   `trading.domain.portfolio_math.strategy_return_pct` (raises `ValueError`), and an inline
   copy in `daily_metrics.py`.
4. **`_normalize_trade_fields`, twice** — same name and signature in `accounting.py` and
   `metrics.py`, with different coercion policies (`row_float(...) or 0.0` versus a raising
   `_coerce_trade_float`).
5. **Market value and unrealized P&L.** `portfolio_math.compute_market_value_and_unrealized`
   computes in one pass what `simulation_math` computes in two, and skips an unpriced ticker
   where `compute_unrealized_pnl` raises.

The risk is the one `trading/domain/bars.py` already names for bar gaps: the simulation and
the live runtime "have to agree ... or the same strategy evaluates differently in a backtest
than it does against the market." That reasoning was applied to bars and not to accounting.

None of the five is currently producing a wrong number. The fractional-quantity gap in
particular is latent: both sides size through `auto_trading_policy.choose_buy_qty`, which
returns `int`.

Alternatives considered:

- **Leave them duplicated and pin the pairs with equality tests.** Cheapest, and keeps the
  contexts independent. Rejected because a test that asserts two implementations agree is a
  standing tax that grows with every metric, and it does not stop a sixth copy appearing.
- **A new sibling package (`src/finance/`) owned by neither context.** Conceptually clean.
  Rejected because the conventions define the criterion for a package beside `trading/` as
  *table ownership*; a math package owns no tables and would not meet the bar the document
  sets. Adopting it would require amending that rule first.
- **`trading/domain/` as the single owner** (chosen). Requires no new package, no change to
  the layering rules, and uses a seam that already exists and is already enforced.

## Decision

Financial math used by both contexts lives in `src/trading/domain/`, and `backtesting`
imports it.

Placement follows what a value *means*, not who happens to need it:

| Kind | Home |
|---|---|
| Unit and scale primitives with no financial meaning (`PERCENT_SCALE`, `BASIS_POINTS_DIVISOR`, `TRADING_DAYS_PER_YEAR`) | `src/common/constants.py` |
| Arithmetic carrying financial meaning shared by live and backtest (ledger updates, return and risk ratios, trade-field coercion) | `src/trading/domain/` |
| Arithmetic only a backtest can perform (equity-curve metrics over a full simulated series, walk-forward window geometry, optimizer objectives) | `src/backtesting/domain/` |

The dividing line for the third row is **whether the live runtime could compute it at all**.
Max drawdown over an equity curve and the `calmar_v1` objective stay in `backtesting/domain/`
because the live side stores only daily snapshots and has no curve to measure — this is why
`daily_metrics.drawdown_pct` is permanently `None`.

`common/` does not become the home for domain math. Its documented role is cross-cutting,
domain-agnostic tooling, and cost-basis accounting is not that.

## Consequences

**Migration, in dependency order.** Each step is independently shippable:

1. Promote `accounting.py`'s `_apply_buy`/`_apply_sell` to public ledger primitives; delete
   `simulation_math.py`'s `update_on_buy`/`update_on_sell` and import them.
2. Collapse the two `_normalize_trade_fields` onto one coercion policy.
3. Give total return one definition with one explicit zero policy; the three current callers
   want different behavior on `initial_cash == 0`, so this reconciles rather than merges.
4. Move Sharpe to `trading/domain/`, taking the pure-Python implementation — `trading` does
   not depend on pandas and should not start.
5. Fold `simulation_math`'s market-value and unrealized-P&L pair into
   `portfolio_math.compute_market_value_and_unrealized`, choosing one missing-mark policy.

**Step 1 changes backtest behavior and must be decided, not assumed.** Adopting the live
primitives brings their guards with them: whole-unit enforcement, and dropping a flat
position's key instead of zeroing it. Whether the backtest should reject fractional
quantities is a real question — the answer is probably yes, since divergence from live is the
defect this ADR exists to close, but it is a behavior change and belongs in its own commit
with its own test.

**What does not move.** The two `bars.py` modules are a deliberate, documented split —
per-frame gap rules in `trading`, multi-ticker calendar alignment in `backtesting` — not a
duplication. `PERCENT_TO_BASIS_POINTS` in `rotation/policy.py` stays distinct from
`PERCENT_SCALE`: same value, different conversion.

**Cost.** `backtesting` depends on more of `trading.domain` than it does today. That is the
direction the seam already permits, and it is the price of the two contexts agreeing on what
a trade costs.

**This rule is not self-enforcing.** `layer_check` validates direction, not duplication —
nothing mechanical will catch a sixth copy. Until something does, this ADR is the check, and
a reviewer noticing a formula being retyped is how it gets applied.
