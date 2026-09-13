# Money Representation Plan: REAL floats to integer minor units

Type: plan
Status: Draft
Created: 2026-09-12
Last Reviewed: 2026-09-12
Purpose: Plan the change from float money and quantity storage to integer minor units with a defined fractional-share precision, before any code is written.
Related: [Database Schema Reference](db-schema.md), [DB Migration System](db-migration-system.md), [Architecture Conventions](../architecture/architecture-conventions.md), [ADR 020 Shared Financial Math Ownership](../adr/020-shared-financial-math-ownership.md)

## Purpose

This document is a plan, not a record of finished work. It defines the scope, the decisions, and a
staged order for the money-representation change. Read it before you write code. No code change is
approved yet. The staged order and the open questions come first.

## Why this change is now in scope

Cash, quantities, and prices are stored as SQLite `REAL` (floats) throughout the schema. This was an
accepted limitation for paper trading. Cameron now intends to trade fractional shares, which turns
the float representation into a live bug:

- The whole-units guard `_require_whole_units` in
  [`domain/accounting/account.py`](../../src/trading/domain/accounting/account.py) rejects any
  fractional quantity today.
- The sizing functions in
  [`domain/auto_trading/sizing.py`](../../src/trading/domain/auto_trading/sizing.py) return whole
  `int` share counts (`choose_buy_qty`, `allocate_buy_quantities`, `closing_sell_qty`).
- `_compact_positions` treats any `qty > 0` as an open position. A fractional float quantity leaves
  float dust after a full sell, which reads as a phantom open position that holds a stale average
  cost.

So the change is two changes that must land together: exact money arithmetic, and defined-precision
fractional share quantities.

This plan **supersedes** the "Money as REAL" note in
[`db-schema.md`](db-schema.md), which still tells readers not to move toward integer cents. Resolve
that contradiction when the design is accepted.

## Scope

The change is large. Do not treat it as a one-session edit.

**Schema.** The baseline revision `0001_current_schema.py` has 92 `REAL` columns. They fall into
money (cash, equity, price, fee, notional, P&L), quantity (share counts), and price-dependent cache
columns (`positions.market_value`, `positions.unrealized_pnl`). Classify every column into money,
quantity, or derived before the migration.

**Code sites.** Every read, write, and accounting site is affected. The known anchors are:

- Domain accounting: `domain/accounting/account.py`, `ledger.py`, `book.py`, `validation.py`.
- Sizing: `domain/auto_trading/sizing.py` (returns whole `int` shares today).
- Execution services: `services/execution/ledger/`, `nav.py`, `equity_reconciliation.py`.
- Analysis: `services/analysis/portfolio.py`, `benchmark.py`.
- Repositories: every `fetch_*`/`insert_*` that reads or writes a money or quantity column.
- Models: `AccountState`, order/position/ledger record and insert models.
- Coercion: `common/coercion.py` `row_float`/`coerce_float`, used at every repository boundary.
- The backtest replay, which shares `normalize_trade_fields` and the apply functions.
- The invariant check `scripts/data_ops/check_cash_invariant.py` (float-tolerance today).

## Decisions to make first

These decisions gate the design. They belong to Cameron. Decisions 3, 4, and 5 are made (see below).
Decisions 1 and 2 wait on the evidence step. Do not start Stage 1 until 1 and 2 are also fixed.

**Recorded direction (2026-09-12): precision is broker-driven, and the two axes have different
drivers.** Two decimals are not enough. Money precision follows what the broker **reports**: an IBKR
commission is sub-cent and an averaged fill price carries many decimals. Quantity precision follows
what the broker lets us **trade**: a finer share fraction than the broker executes is not worth
storing. So fix both numbers from evidence, not from a guess — see the evidence step below.

1. **Money scale.** Choose the integer minor unit for money, fine enough to hold a reported
   commission and an averaged fill price without truncation. Cents (`1e-2`) truncate both. A finer
   scale (for example `1e-4` of a dollar, or micro-dollars `1e-6`) holds them exactly. Pick one scale
   and apply it to every money column.
2. **Quantity precision.** Choose the decimal precision for a share quantity, matched to the broker's
   fractional-order granularity — no finer. Fractional shares need a defined precision, not an open
   float.
3. **In-memory type. Decided (2026-09-12): a custom `Money`/`Quantity` value object.** Each object
   wraps an `int` minor-unit count and owns its scale. It keeps the scale in one place and blocks a
   raw-float mix at the type level. Do not compute money with bare `int`, `float`, or `Decimal` in
   the domain.
4. **Rounding rule. Decided (2026-09-12): truncate toward zero, through one swappable policy.** A
   division or a percentage sizing result truncates toward zero to the minor unit. Apply it through a
   single named rounding function or constant, documented so the rule can be changed without touching
   every call site. Do not scatter raw `int()` truncations across the code.
5. **Migration data path. Decided (2026-09-12): type-only, no value conversion.** Staging and prod
   will be reset, and dev resets too, so every accounting table is empty at migration time. The
   revision changes the classified columns from `REAL` to `INTEGER` and needs no data conversion
   (see [`db-migration-system.md`](db-migration-system.md)).

## Staged plan

Keep each stage small and green. This order follows the "inject first, move the adapter last"
convention in the architecture guide.

1. **Stage 0 — decide.** Record the answers to the five decisions above in this document. Then
   promote the accepted decision to an ADR.
2. **Stage 1 — the type.** Add the `Money`/`Quantity` value type (or the chosen representation) at
   its lowest owning layer, plus a persistence encoder and decoder. The `persistence/` package owns
   column encoding and currently has no such module, so it is the natural home. Storage stays float
   in this stage; the type flows through the domain only.
3. **Stage 2 — accounting.** Convert `domain/accounting/` and the sizing functions to the new type.
   Keep the whole-units guard until Stage 4. Prove the backtest replay still matches.
4. **Stage 3 — schema.** Author the numbered revision that changes the classified columns from
   `REAL` to `INTEGER`. Wire the encoder to write and read integers. Update
   `EXPECTED_HEAD_REVISION` in the same commit.
5. **Stage 4 — fractional shares.** Remove `_require_whole_units`, let sizing return fractional
   quantities at the chosen precision, and update the exact-zero position check to the new
   precision. Update `check_cash_invariant` to an exact integer check.
6. **Stage 5 — docs and tests.** Rewrite the "Money as REAL" note in `db-schema.md`, regenerate the
   schema diagram, and add tests for the encoder, the rounding rule, and a fractional round trip.

## Boundaries

- Do not weaken the Live Trading Safety Guard. The migration must never set
  `live_trading_enabled = 1` or touch a broker column.
- Do not hand-write value conversion into a revision without explicit human review
  (see the migration authoring rules).
- Keep money math in `domain/`; `common/` keeps unit scales only (ADR 020).

## Evidence step (resolves the money scale and quantity precision)

Before you fix the two scales, capture the real precision from the broker. The socket adapter
[`ibkr_socket/adapter.py`](../../src/infrastructure/brokers/ibkr_socket/adapter.py) already surfaces
the fields as floats: `fill.price`, `fill.commission`, `trade.avg_fill_price`, and `fill.shares`.

1. Place one fractional-share order against an IBKR paper account.
2. Read the observed decimal count of `fill.price`, `fill.commission`, `avg_fill_price`, and
   `fill.shares` from the reconciled fill.
3. Set the money scale from the finest reported money value, and the quantity precision from the
   smallest fractional share the broker accepts and reports.

## Open questions

- Do any external feeds or reports expect a float money value at their boundary, and where must the
  value convert back to a display float?

## Related Docs

- [Database Schema Reference](db-schema.md) — the money columns and the note this plan supersedes
- [DB Migration System](db-migration-system.md) — revision authoring rules and the rollout procedure
- [ADR 020 Shared Financial Math Ownership](../adr/020-shared-financial-math-ownership.md) — where money math and unit scales live
