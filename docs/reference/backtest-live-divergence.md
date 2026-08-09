# Backtest / Live Execution Divergence

Type: notes
Status: Active
Created: 2026-08-01
Last Reviewed: 2026-08-06
Purpose: Record where the simulation engine and the live runtime execute differently, what that does to walk-forward selection given how the optimizer is meant to be used, and which gaps are bugs versus open design decisions.
Related: [Backtesting](backtesting.md), [Broker Integration](broker-integration.md), [IBKR Paper Execution Plan](ibkr-paper-execution-plan.md), [Runtime Jobs](runtime-jobs.md)

## Purpose

Found during the `features/auto-trading-updates` review (2026-08-01). That branch went to
considerable lengths to make live and backtest evaluate the same *signal* — bars instead of closes,
one shared `evaluate_signal_over_bars`, identical gap-filling in `trading.domain.bars`. It did not
touch what either side does *with* a signal, and that is where they diverge most.

Read this before trusting a walk-forward result, before changing the live exit path, and before
raising any trade cap.

**Status of the defects below: fixed on 2026-08-06.** The five items previously listed under
*Bugs* — the sliced exit, the tied stop/target priority, the single sampled breach, the
un-closable position, and the caps that never bound — have all landed, along with the broker-pacing
count. Each section keeps its original description of the defect so the reasoning survives; what
changed is recorded inline. The **open decisions** below are still open and were deliberately not
resolved by that work.

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

| | Backtest | Live (before) | Live (now) |
|---|---|---|---|
| Trades per bar | every signalled buy and sell | one, per book, per run | up to the book's budget |
| Sell on signal | closes the full position | 1–5 shares, randomly | closes the full position |
| Risk stops | not modelled | fire, then sell 1–5 shares | fire, then close the position |
| Buy sizing | `choose_buy_qty` + proportional allocation | `choose_buy_qty` — same policy | same, and now the same allocation |

Buys agree on both axes: both sides call `choose_buy_qty` to size and `allocate_buy_quantities` to
fund. Live reached the allocation case only once a book could emit more than one buy in a run, which
is why the two landed together.

Risk stops remain unmodelled by the engine — that is **open decision 2**, not a defect fixed here.

### Sells close the position in simulation, trim it live

[`simulation_service.py`](../../src/backtesting/services/simulation_service.py) sells the
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

**Fixed.** `choose_sell_qty` and `MAX_ORDER_QTY` are gone; `closing_sell_qty` returns the whole
position, so a live sell exits the same way the engine's does.

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

**Fixed.** `order_risk_breaches` replaces it, returning *every* breach: stop-losses first, then
take-profits, each group ordered by distance past its threshold. No randomness, so the ordering
reproduces from the audit trail. With a real per-book budget, more than one breach can now be acted
on in the same run.

### Positions can never fully close

Because `choose_sell_qty` caps at 5 unconditionally, no live sell ever closes a position outright. A
20-share position needs at least four runs to exit; 100 shares needs at least twenty.

**Fixed** by the same change: a sell closes the position. The leaps-only `min(qty, 2)` cap went with
it — it was the same defect in contracts rather than shares.

### One trade per book per run, and the caps that never bind

`prepare_trade_selection` returns a single trade, so each book contributes at most one intent, and
`max_intents = min(max_trades, len(trading_books))`
([`book_intents.py:69`](../../src/trading/services/execution/selection/book_intents.py)).

Two surfaces configure a larger number. Neither reaches execution:

| Surface | Configured | Effect |
|---|---|---|
| `books.max_trades_per_run` | per book; in web UI, account API, optimizer manifest | **never read by the execution path** |
| `--primary-max-trades` / `--other-max-trades` | defaults 5 / 11 | only as `min(cap, book_count)` |

A third surface, src/infrastructure/config/account_trade_caps.json, set `default: 11` with
momentum/meanrev at `5`. It was deleted along with its loader; because it took precedence over the
two CLI flags, it had also made them unreachable.

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

**Fixed.** `prepare_book_trades` returns a list, so a book emits up to its own budget. The account
cap counts trades rather than books, and `books.max_trades_per_run` narrows that within a book
(`NULL` = no book-level limit). Sells still run first, and their proceeds fund the same run's buys.

Two things follow, both live now:

- The 5 / 11 split binds for the first time. See open decision 3 — it has never been tested.
- The per-minute throttle became load-bearing, so it moved inside `submit_book_intents` and runs
  between orders rather than once per book.

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

### Bugs — all fixed 2026-08-06

1. ~~A forced sell should close the position rather than draw 1–5 shares.~~
2. ~~A stop-loss breach should outrank a take-profit breach rather than tie.~~
3. ~~Every breached position should be considered, not one sampled at random.~~
4. ~~A signalled sell should be able to close a position.~~
5. ~~`books.max_trades_per_run` should bind, and the account-level cap should cap trades rather
   than books.~~

### Open decisions — still open

1. Whether sells should keep absolute priority over buys once a book has a real budget. The budget
   is now real and sells still go first, which is the status quo carried forward, **not** a decision
   that this is right.
2. Whether the engine models risk stops. While it does not, promotion selects on a number that
   excludes the exit machinery live actually uses. Unchanged — the exit fixes made live behave as
   its names say, they did not teach the engine about stops. If anything this widens the gap: live
   exits decisively now, and the engine still never stops out.
3. Whether the 5 / 11 account cap split — tighter on the two 5k accounts — was a considered risk
   choice. **It binds as of item 5 landing**, so it is now live and still untested.

## Trade budget and broker pacing

Related, because the per-book budget is the mechanism that fixes axis 2, and raising it is what
makes pacing matter.

`enforce_runtime_trade_throttles` records an audit block when exceeded and stops the run. Both of
its caps (`runtime_max_trades_per_day`, `runtime_max_trades_per_minute`) are unset, so it is a no-op
today.

**One defect mattered for broker pacing.** `fetch_fill_count_between` counts rows in `order_fills`
by `fill_time`. Against `PaperBrokerAdapter`, fills are instantaneous and this reads like
submissions. Against the IBKR socket an order may sit unfilled indefinitely — so a run could submit
any number of orders in a minute while the fill count stays at zero and the per-minute cap never
fires. The per-minute cap is the broker-pacing protection, and it was blind to precisely the brokers
that can be overwhelmed.

**Fixed.** The per-minute cap counts `orders.submitted_at` via `fetch_submission_count_between`; the
per-day cap keeps counting fills, since that measures realized trading. The check also moved into
`submit_book_intents` and runs between orders rather than once per book — moot while a book emitted
one intent, load-bearing now that the budget is real. A throttled book reports `throttled` so the
run stops submitting for later books too.

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
