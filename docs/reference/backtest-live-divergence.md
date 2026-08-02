# Backtest / Live Execution Divergence

Type: notes
Status: Active
Created: 2026-08-01
Last Reviewed: 2026-08-01
Purpose: Record where the simulation engine and the live runtime execute differently, which of those gaps are bugs and which are open design decisions, and what has to be settled before a backtest number can be read as a prediction.
Related: [Backtesting](backtesting.md), [Broker Integration](broker-integration.md), [IBKR Paper Execution Plan](ibkr-paper-execution-plan.md), [Runtime Jobs](runtime-jobs.md)

## Purpose

Found during the `features/auto-trading-updates` review (2026-08-01). That branch went to
considerable lengths to make live and backtest evaluate the same *signal* — bars instead of closes,
one shared `evaluate_signal_over_bars`, identical gap-filling in `trading.domain.bars`. It did not
touch what either side does *with* a signal, and that is where they diverge most.

Read this before treating a walk-forward return as an estimate of live performance, and before
changing the live exit path.

## The two statements this document exists to make

**1. The backtest and the live runtime execute different strategies.** Not the same strategy with
execution noise — different position sizing on exit, a different number of trades per bar, and risk
stops on one side only. A backtest return describes a more aggressive, unprotected strategy than
the one the runtime actually trades. This is not a conservative bias in a known direction; it is a
different thing being measured.

**2. Part of the gap is a bug, not a design difference.** The live exit path does not do what its
names say — a stop-loss does not stop out. Those defects are fixable on their own terms, without
first deciding how the two paths should be reconciled. Fixing them narrows the gap but does not
close it.

## Overview

Signal *generation* is shared. Signal *execution* is not.

| | Backtest | Live |
|---|---|---|
| Trades per bar | every signalled buy and sell | one, per book, per run |
| Sell on signal | closes the full position | 1–5 shares, randomly |
| Risk stops | not modelled | fire, then sell 1–5 shares |
| Buy sizing | `choose_buy_qty` + proportional allocation | `choose_buy_qty` — same policy |

Buys are the one axis that agrees, and only because both call the same policy function.

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

`forced_sell` — the stop-loss / take-profit pick — goes through the same
`prepare_sell_trade` loop as an ordinary signalled sell. It is granted priority in the ordering and
then sized by the same `choose_sell_qty`. **A stop-loss sells 1–5 shares.**

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

### Sells starve buys

`prepare_trade_selection` returns on the first prepared sell, and a book contributes at most one
intent per run (`max_intents = min(max_trades, len(trading_books))`,
[`book_intents.py:69`](../../src/trading/services/execution/selection/book_intents.py)). So any book
with a live sell signal or a breached stop does no buying that day.

Combined with the previous point, a book trickling out of one position blocks its own buy side for
weeks.

## Boundaries

### Bugs — fixable without the alignment decision

These are wrong on their own terms. None requires agreeing on what the backtest should model.

1. A forced sell should close the position (or a configured fraction of it) rather than draw 1–5
   shares from it.
2. A stop-loss breach should outrank a take-profit breach rather than tie.
3. Every breached position should be considered, not one sampled at random.
4. A signalled sell should be able to close a position.

### Open decisions — need the alignment conversation first

These are legitimately arguable, and the answers change what the backtest must model.

1. **One trade per book per run.** Deliberate throttle for paper burn-in, or an artifact? If it is
   deliberate, the backtest has to adopt it — this is the single largest reason live will not
   reproduce backtest returns.
2. **Sells taking absolute priority over buys** within a one-trade budget.
3. **Whether the engine models risk stops at all.** While it does not, walk-forward promotion
   selects strategies on a number that excludes the exit machinery live actually uses.

### Three ways to close it

- **Move live toward the backtest** — full exits, act on all signalled buys per run, add stop
  modelling to the engine. Makes backtest numbers meaningful; largest change to live behaviour.
- **Move the backtest toward live** — one trade per book per bar, trim-style sells, model the
  stops. Faithful, but optimizes a strategy whose exit mechanics are arbitrary, and slows sweeps.
- **Reframe** — treat the engine as a signal evaluator rather than a portfolio simulator and stop
  reading its returns as predictive.

The third is the current de-facto position, arrived at without being chosen. Promotion gates read
these returns as predictive today (`evaluate_promotion_gate` compares OOS and holdout returns), so
leaving it unstated is the part worth correcting regardless of which option wins.

## Status

Nothing here is scheduled. No account has traded — every account is `broker_type='paper'` and the
`orders` table is empty as of 2026-08-01 — so none of this has cost anything yet. It matters before
the first non-`paper` account, which is what
[ibkr-paper-execution-plan.md](ibkr-paper-execution-plan.md) is working toward.

## Related Docs

- [Backtesting](backtesting.md) — engine, walk-forward geometry, promotion gate
- [IBKR Paper Execution Plan](ibkr-paper-execution-plan.md) — the path to a non-`paper` account
- [Broker Integration](broker-integration.md) — broker types and their guards
- [Rotation Scoring](rotation-scoring.md) — the other consumer of backtest performance numbers
