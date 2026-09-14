# Money Representation Plan: REAL floats to integer minor units

Type: plan
Status: Draft
Created: 2026-09-12
Last Reviewed: 2026-09-12
Purpose: Plan the change from float money and quantity storage to integer minor units with a defined fractional-share precision, before any code is written.
Related: [Database Schema Reference](db-schema.md), [DB Migration System](db-migration-system.md), [Architecture Conventions](../architecture/architecture-conventions.md), [ADR 015 Numbered Alembic Migrations](../adr/015-numbered-alembic-migrations.md), [ADR 020 Shared Financial Math Ownership](../adr/020-shared-financial-math-ownership.md)

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
3. **In-memory type. Decided (2026-09-12): `decimal.Decimal`.** The domain computes money and
   quantity with `Decimal`, which gives exact arithmetic from the standard library and kills the
   float dust. A single shared truncation helper applies the rounding rule (decision 4), and the
   persistence encoder converts `Decimal` to and from the integer minor unit at the repository
   boundary. A typed `Money`/`Quantity` wrapper was considered and **deferred**: its benefit is
   unit-mixing safety and a compile-time scale guard, not precision, so it stays a cheap
   non-breaking add-on if a real unit-mixing bug appears. See
   [Storage representation](#storage-representation).
4. **Rounding rule. Decided (2026-09-12): truncate toward zero, through one swappable policy.** A
   division or a percentage sizing result truncates toward zero to the minor unit. Apply it through a
   single named rounding function or constant, documented so the rule can be changed without touching
   every call site. Do not scatter raw `int()` truncations across the code.
5. **Migration data path. Decided (2026-09-12): type-only, no value conversion.** Staging and prod
   will be reset, and dev resets too, so every accounting table is empty at migration time. The
   revision changes the classified columns from `REAL` to `INTEGER` and needs no data conversion
   (see [`db-migration-system.md`](db-migration-system.md)).

## Storage representation

**Storage stays integer minor units, not `Decimal`-as-`TEXT`.** SQLite has no decimal type. Its
affinities are `INTEGER`, `REAL`, `TEXT`, `BLOB`, and `NUMERIC`. A `TEXT` decimal is storable and
exact for a single value, and it needs no chosen scale. It is rejected for one concrete reason: the
app does money math **in SQL**, and `TEXT` breaks it.

- `repositories/snapshots.py` rolls per-book equity snapshots into an account view with SQL
  `SUM(cash)`, `SUM(market_value)`, `SUM(equity)`, `SUM(realized_pnl)`, and `SUM(unrealized_pnl)`,
  and takes `MAX(equity)` for the peak that drives drawdown.
- `scripts/data_ops/check_cash_invariant.py` sums `ledger.amount` in SQL.

On a `TEXT` column SQLite coerces `SUM(...)` to **float** — the aggregate reintroduces the float
error we are removing — and compares `MAX`/`ORDER BY`/ranges **lexicographically**, so `"9" > "100"`
and the peak is wrong. To keep `TEXT`, every such aggregation must move into Python, which is a real
refactor and a standing "no SQL money aggregation" rule. Integer minor units keep the SQL exact and
correct; their only cost is a fixed scale, which is a one-time number set from the evidence step.

**The conversion lives in one place: a persistence-layer encoder and decoder at the repository
boundary.** Repositories already cross there — `execute(...)` to `dict(row)` to
`Model.from_mapping(...)` on the way in, and an insert tuple on the way out. The encoder decodes an
integer column to a `Decimal` and encodes a `Decimal` back to an integer at the fixed scale, so no
caller hand-converts. `persistence/` owns column encoding and has no such module yet, so it is the
home.

**SQLAlchemy does not apply here, and we investigated it (2026-09-12).** The suggestion was to let
SQLAlchemy map a `Decimal` to a database representation automatically. This repo does not use
SQLAlchemy at runtime by explicit decision:

- SQLAlchemy and Alembic are **ops-only** dependencies (`requirements-dev.txt`). The only runtime
  imports outside the Alembic directory are `create_engine`/`StaticPool` in the ops-only
  `migration_runner.py`. The application has no ORM and no model metadata
  ([ADR 015](../adr/015-numbered-alembic-migrations.md)).
- The runtime path is raw `sqlite3`: `sqlite3.connect`, `row_factory = sqlite3.Row`, and repository
  `execute(...)` calls.
- On SQLite, SQLAlchemy does not preserve a `Decimal` for free anyway. Its `Numeric` type processes
  as float on the pysqlite dialect and warns about precision loss, so exact storage still needs a
  hand-written `TypeDecorator` (`Decimal` to `TEXT` or scaled `int`) — the same conversion the
  boundary encoder does.

So adopting SQLAlchemy would reverse ADR 015 and add an ORM the app does not have, to gain a
per-column hook that on SQLite still needs a custom type. The boundary encoder is that hook without
the ORM. Do not add SQLAlchemy to the runtime.

## Staged plan

Keep each stage small and green. This order follows the "inject first, move the adapter last"
convention in the architecture guide.

1. **Stage 0 — decide.** Record the answers to the five decisions above in this document. Then
   promote the accepted decision to an ADR.
2. **Stage 1 — the encoder.** Add the persistence encoder and decoder (`Decimal` to and from the
   integer minor unit) and the shared truncation helper at their lowest owning layers. `persistence/`
   owns column encoding and has no such module yet, so it is the home. Storage stays float in this
   stage; `Decimal` flows through the domain only. The scale can start as a named provisional
   constant and be finalized once the evidence step lands.
3. **Stage 2 — accounting.** Convert `domain/accounting/` and the sizing functions to `Decimal`.
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
