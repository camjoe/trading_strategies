# Backtest / Live Execution Divergence

Type: notes
Status: Active
Created: 2026-08-01
Last Reviewed: 2026-08-01
Purpose: Record where the simulation engine and the live runtime execute differently, what that does to walk-forward selection given how the optimizer is meant to be used, and which gaps are bugs versus open design decisions.
Related: [Backtesting](backtesting.md), [Broker Integration](broker-integration.md), [IBKR Paper Execution Plan](ibkr-paper-execution-plan.md), [Runtime Jobs](runtime-jobs.md)

## Purpose

Found during the `features/auto-trading-updates` review (2026-08-01). That branch went to
considerable lengths to make live and backtest evaluate the same *signal* — bars instead of closes,
one shared `evaluate_signal_over_bars`, identical gap-filling in `trading.domain.bars`. It did not
touch what either side does *with* a signal, and that is where they diverge most.

Read this before trusting a walk-forward result, before changing the live exit path, and before
raising any trade cap.

**Everything below describes `develop`.** Every defect named here is pre-existing — `MAX_ORDER_QTY`,
both random draws in the risk-exit path, and the `min(max_trades, book_count)` intent cap are all
present and unmodified on the base branch. The one item this branch introduces is the engine-side
proportional buy allocation noted under Overview.

## Intended use of walk-forward

Recorded because it determines which divergences matter. The optimizer exists to:

1. **Test candidate strategies** — periodically on a schedule, or on demand when an operator wants
   to try something.
2. **Decide whether a trading account should switch strategy, or keep its strategy with different
   parameters.**

Both are *comparative* — ranking candidates — rather than absolute forecasts of return. That is a
weaker requirement than predicting live performance, and it would be easy to conclude the
divergences therefore do not matter much. They do, for the reason in the next section.

## The two statements this document exists to make

**1. The divergence is a selection bias, not a level error.** If the engine simply returned numbers
that were uniformly too high, comparison would survive it — every candidate would be inflated
equally and the ranking would hold. It does not work that way. The gap scales with turnover and
signal breadth, which are exactly the properties that differ between the strategies being ranked.

**2. Part of the gap is a bug, not a design difference.** The live exit path does not do what its
names say — a stop-loss does not stop out. Those defects are fixable on their own terms, without
first settling how the two paths should be reconciled.

## Overview

Signal *generation* is shared. Signal *execution* is not.

| | Backtest | Live |
|---|---|---|
| Trades per bar | every signalled buy and sell | one, per book, per run |
| Sell on signal | closes the full position | 1–5 shares, randomly |
| Risk stops | not modelled | fire, then sell 1–5 shares |
| Buy sizing | `choose_buy_qty` + proportional allocation | `choose_buy_qty` — same policy |

Buys are the one axis that broadly agrees, because both call the same sizing policy. The engine adds
proportional allocation when cash cannot fund every buy signal on a bar (`allocate_buy_quantities`,
new on this branch). Live never reaches that case: a book emits one trade per run, so there is
nothing to allocate between. The gap opens only once a real per-book budget lands.

### Sells close the position in simulation, trim it live

[`execution_service.py:135`](../../src/trading/backtesting/services/execution_service.py) sells the
whole position on a sell signal:

```python
qty_float = float(state.positions[ticker])
```

[`selection.py:386`](../../src/trading/services/execution/selection/selection.py) sells
`choose_sell_qty(...)`, which is `random.randint(1, min(MAX_ORDER_QTY, qty))` with
`MAX_ORDER_QTY = 5` ([`auto_trading_policy.py:15`](../../src/trading/domain/auto_trading_policy.py)).

`choose_sell_qty` has exactly one call site. `MAX_ORDER_QTY` carries no history beyond the
`trading/` → `src/trading/` relocation, which places it before the current book/strategy design —
it reads as a leftover from an early randomized-exploration trader rather than a current decision.

### The risk stop does not stop out

`forced_sell` — the stop-loss / take-profit pick — goes through the same `prepare_sell_trade` loop
as an ordinary signalled sell. It is granted priority in the ordering and then sized by the same
`choose_sell_qty`. **A stop-loss sells 1–5 shares.**

On a 100-share position that leaves the position open and still below its stop, so it fires again
the next run for another 1–5 shares. Exiting takes on the order of 30 trading days at the average
draw, while the position continues to move against the book. The backtest never surfaces this,
because it does not model stops at all.

Two further defects in the same path
([`auto_trading_policy.py:245`](../../src/trading/domain/auto_trading_policy.py)):

- `choose_sell_ticker_by_risk` returns `random.choice(...)` over the breached positions, so when
  three positions breach, two are ignored entirely that run.
- Stop-loss breaches and take-profit breaches are appended to one list and chosen between at
  random. A position down past its stop and one up past its target are treated as equally urgent.

### Positions can never fully close

Because `choose_sell_qty` caps at 5 unconditionally, no live sell ever closes a position outright. A
20-share position needs at least four runs to exit; 100 shares needs at least twenty.

### One trade per book per run, and the caps that never bind

`prepare_trade_selection` returns a single trade, so each book contributes at most one intent, and
`max_intents = min(max_trades, len(trading_books))`
([`book_intents.py:69`](../../src/trading/services/execution/selection/book_intents.py)).

Three surfaces configure a larger number. None reaches execution:

| Surface | Configured | Effect |
|---|---|---|
| `account_trade_caps.json` | `default: 11`; momentum/meanrev `5` | only as `min(cap, book_count)` |
| `books.max_trades_per_run` | per book; in web UI, account API, optimizer manifest | **never read by the execution path** |
| `--primary-max-trades` / `--other-max-trades` | defaults 5 / 11 | same `min(...)` |

Measured against the live database on 2026-08-01: every one of the 8 accounts has exactly one
trading book, so `max_intents = min(cap, 1) = 1` for all of them. The configured caps of 5 and 11
never bind, and the whole system makes at most 8 trades per day regardless of what those numbers
say.

`books.max_trades_per_run` is the clearest evidence this is not deliberate: it is plumbed through
the repository, model, book configuration, parameters view, account API, web UI, and the optimizer's
manifest — everywhere except the one place that would give it effect.

Combined with the exit defects above, this is also what makes sell-starvation severe. It is not
"sells take priority within a budget of 11"; it is that the account's *single* trade goes to the
sell. A book trickling out of one position at a few shares a day does nothing else for weeks.

## What this does to walk-forward selection

Given the intended use above, these are the axes that distort a *comparison*, ranked by how much:

1. **Exits, via turnover.** The engine credits a clean full exit that live cannot perform. A
   strategy whose edge lives in frequent, decisive exits — mean reversion, anything short-horizon —
   is flattered in proportion to its turnover. A slow trend-follower is barely affected. The
   optimizer therefore prefers high-turnover strategies for a reason that is an artifact of the
   engine.
2. **Breadth, via trades per run.** The engine acts on every signal each bar; live takes one per
   book per run. A strategy firing many simultaneous signals is credited for all of them and will
   execute one. Over-credited in proportion to signal density.
3. **Risk stops.** The engine models none, so a strategy that would be repeatedly stopped out live
   shows a clean record. This one is invisible rather than merely wrong: the interaction between a
   strategy and the book's risk policy does not appear in selection at all.

### Fit for purpose, today

- **Parameter tuning within one primitive is largely defensible.** The same primitive at different
  windows has a similar turnover and breadth profile, so the distortion applies to both candidates
  roughly equally and the ranking mostly survives. The exception worth watching: a parameter that
  itself changes turnover — a tighter threshold producing more signals — reintroduces axis 1
  directly.
- **Cross-strategy promotion is not.** That is exactly where turnover and breadth vary most, and it
  is where `evaluate_promotion_gate` is pointed.

### The target is strategy-neutrality, not identity

The engine does not need to predict live returns in absolute terms to serve its stated purpose. It
needs its divergence from live to be **the same for every candidate it ranks**. That is a much
smaller target than making the two paths identical, and it is what should scope any future work.

Two directions remain available, and the choice can be made per axis rather than wholesale:

- **Move live toward the engine** — full exits, honour a real per-book trade budget. Also fixes the
  bugs.
- **Move the engine toward live** — model the trade budget and the risk stops. Necessary for axis 3
  regardless, since live has stops and the engine cannot represent their cost without modelling
  them.

### Measure before choosing

Re-run one existing optimizer sweep with the engine's sell changed to trim-style, and see whether
the ranking moves. A stable winner across both execution models means the bias is tolerable for now
and the work can be deferred; a flipped winner is a measured answer rather than an argument. This is
substantially cheaper than either direction above and should come first.

## Boundaries

### Bugs — fixable without settling anything

1. A forced sell should close the position (or a configured fraction) rather than draw 1–5 shares.
2. A stop-loss breach should outrank a take-profit breach rather than tie.
3. Every breached position should be considered, not one sampled at random.
4. A signalled sell should be able to close a position.
5. `books.max_trades_per_run` should bind, and `account_trade_caps` should cap trades rather than
   books.

### Open decisions

1. Whether sells should keep absolute priority over buys once a book has a real budget.
2. Whether the engine models risk stops. While it does not, promotion selects on a number that
   excludes the exit machinery live actually uses.
3. Whether the 5 / 11 account cap split — tighter on the two 5k accounts — was a considered risk
   choice. It has never bound, so it has never been tested; it becomes real the moment item 5 above
   lands.

## Trade budget and broker pacing

Related, because the per-book budget is the mechanism that fixes axis 2, and raising it is what
makes pacing matter.

`enforce_runtime_trade_throttles` is wired correctly: checked per book before submission, breaks
out of the loop when exceeded, and records an audit block
([`runtime.py:179`](../../src/trading/services/auto_trading/runtime.py)). Both of its caps
(`runtime_max_trades_per_day`, `runtime_max_trades_per_minute`) are unset, so it is a no-op today.

**One defect matters for broker pacing.** `fetch_fill_count_between` counts rows in `order_fills` by
`fill_time`. Against `PaperBrokerAdapter`, fills are instantaneous and this reads like submissions.
Against the IBKR socket an order may sit unfilled indefinitely — so a run could submit any number of
orders in a minute while the fill count stays at zero and the per-minute cap never fires. The
per-minute cap is the broker-pacing protection, and it is blind to precisely the brokers that can be
overwhelmed. It should count submissions (`orders.submitted_at`); the per-day cap can keep counting
fills, since that measures realized trading.

The throttle is also checked once per book rather than between orders. That is moot while a book
emits one intent and stops being moot as soon as the budget is real.

**Scale, for sizing these:** 8 accounts × 1 book. At `max_trades_per_run = 5` that is 40 orders per
run, once a day — negligible for any broker API. The pacing risk arrives with Phase 4 intraday
repeats (40 × N passes), not before. Confirm IBKR's published pacing limits before choosing a
per-minute number rather than guessing.

## Status

Nothing here is scheduled. No account has traded — every account is `broker_type='paper'` and the
`orders` table is empty as of 2026-08-01 — so none of it has cost anything yet. It matters before
the first non-`paper` account, which is what
[ibkr-paper-execution-plan.md](ibkr-paper-execution-plan.md) is working toward.

Open for a later deep dive: whether the intended use above is still the goal, or whether the goal
should be narrowed to something the engine can support sooner.

## Related Docs

- [Backtesting](backtesting.md) — engine, walk-forward geometry, promotion gate
- [IBKR Paper Execution Plan](ibkr-paper-execution-plan.md) — the path to a non-`paper` account
- [Broker Integration](broker-integration.md) — broker types and their guards
- [ADR 019: Rotation Score Components](../adr/019-rotation-score-components.md) — the other consumer of backtest performance numbers
