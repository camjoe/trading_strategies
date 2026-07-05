# Implementation Guide — P4: Converge accounts & sleeves on the clean book schema

Type: implementation
Status: Ready (large; multi-commit; safety-critical — touches the live submission path)
Purpose: Work order for P4 — build the shared submission/accounting/rotation services once on the
clean book schema, starting with 2a (the shared order-submission service). Ordered phases, each a
green commit.
Initiative: P4 (Converge accounts & sleeves)
Estimate: L
Created: 2026-07-05
Last Reviewed: 2026-07-05
Related: [Plan](../plan.md), [Sleeves & Accounts Convergence Plan](../sleeves-accounts-convergence.md),
[Decisions](../decisions.md), [DB Schema Target](../db-schema-target.md),
[Architecture Conventions](../architecture/architecture-conventions.md),
[ADR 003 — Sleeve Virtualization](../adr/003-sleeve-virtualization-architecture.md),
[Implementation README](README.md)

> Follows the [operating model + execution protocol](README.md) and the P1/P3 house style. P4 is the
> convergence spine built **once on the clean schema** (P3 delivered the tables + repositories; they
> are currently empty). It is **safety-critical**: it rewires how paper/live orders are submitted and
> persisted. Steps are marked **[strong]** (design/logic — strong model or careful human review) or
> **[light]** (mechanical). Do them in order; each is its own green commit.

## 1. Objective

Replace the two parallel trade-submission paths — account mode
(`_broker_aware_record_trade` → `broker_orders` + `record_trade`) and sleeve mode (inline loop in
`_run_sleeve_mode_for_account` → `sleeve_orders` + `apply_sleeve_fill` + `record_trade`) — with **one
shared submission service** that writes the clean book-keyed tables (`orders`, `order_fills`,
`positions`, `ledger`) and owns the pre-submit safety gates centrally, so every book inherits them.

Under the clean schema a "mode" is just default-book (plain account) vs multi-book (sleeved account);
the service operates on one **strategy-book** contract with no per-mode persistence branching.

This work order details **2a** (the shared submission service) in full and sketches **2c** (unified
accounting/ledger) and **2b** (unified rotation/selection), which follow. Internal order: **2a → 2c
→ 2b**, with the P5 naming pass alongside 2b.

### Definition of Done (2a)
- [ ] One `trading.services.execution` service (new `services/execution` package) submits a book's approved intents: pre-submit gate →
      `broker.place_order` → persist to clean `orders`/`order_fills` → on fill, update
      `positions` + `ledger` — all keyed by `book_id`.
- [ ] The pre-submit safety gates (stale-price, reconciliation mismatch/staleness/missing,
      broker-API anomaly kill switches) are owned centrally as an **injected gate policy** and apply
      to **every** book — account mode is no longer missing the kill switches sleeve mode had.
- [ ] Account mode and sleeve mode both submit through the service; no path re-implements
      submit/persist/on-fill.
- [ ] Open-order reconciliation reads the clean `orders`/`order_fills` (moved off `broker_orders` /
      `sleeve_orders` in lockstep with the cutover).
- [ ] The legacy submission writers (`_broker_aware_record_trade`, the inline sleeve loop,
      `sleeve_orders`/`sleeve_fills` writes) are retired; legacy-table drops are staged as the final
      cleanup once nothing reads them.
- [ ] `python -m scripts.run_checks ci` green. Plan P4/2a status updated; convergence-plan progress
      log appended.

## 2. Preconditions
- Branch off the latest `develop` (P3 merged — clean book schema + repositories exist and are empty
  of writes). `./.venv` exists.
- Read `docs/architecture/architecture-conventions.md` (layering; the Live Trading Safety Guard) and
  ADR 003 before touching submission.
- Decisions locked (this guide encodes them — see §5).

## 3. Guardrails (safety-critical)
- **Never** set `live_trading_enabled`; never construct brokers inline — always use the injected
  `broker_factory` / injected broker.
- **Safety only strengthens.** When the two paths merge, the stricter path's guards (sleeve kill
  switches) become the shared default. Never drop a kill switch to make merging easier — account mode
  *gains* them.
- Behavior change is intended for the persistence target (legacy tables → clean book-keyed tables),
  but the trade-decision policy, sizing, and risk-gate *math* are unchanged — reuse the existing
  domain policies; do not re-derive them.
- Keep SQL in repositories; the execution service orchestrates repositories + the broker port only.
- If a step needs a decision not covered by §5 → **stop and report**; do not improvise on the live
  path.

## 4. Branch & commit strategy
- Dedicated branch (e.g. `features/phase4-sleeve-book-consolidation`, already created).
- **One commit per phase below**, each after its checks are green. Never commit on red.
- Commit message: summary + body + the executing model's own `Co-Authored-By` line.

## 5. Design decisions resolved
- **Package:** a new `trading.services.execution` package (`services/execution`) owns submission +
  on-fill ledger + the pre-submit gate seam. Keeps `auto_trading` focused on orchestration (SRP).
  *(Decided 2026-07-05.)*
- **Safety-gate ownership:** the service accepts an **injected pre-submit gate policy** (a callable /
  small protocol returning approved/blocked/rescaled intents + kill-switch reasons), rather than
  hard-coding the gates. Book-specific or environment-specific gates stay pluggable and unit-testable.
  *(Decided 2026-07-05.)*
- **Surviving rotation paradigm (for 2b, not 2a):** champion/challenger on the decision-score
  contract survives; the account-episode path retires. Confirm during 2b. *(Per the convergence
  plan's open question; recorded here so 2b has no ambiguity.)*

## 6. Build plan — 2a (ordered; each a green commit)

### Phase 2a-1 — Execution service + intent contract, in isolation  **[strong]**
- New package under `services/execution` (i.e. `trading.services.execution`) with:
  - a normalized `BookTradeIntent` (or reuse — `book_id`, `account_id`, `strategy_id`, `symbol`,
    `side`, `qty`, `requested_price`, `order_type="market"`, `time_in_force="day"`), in
    `models/` if it is passive data;
  - a `PreSubmitGate` protocol: `evaluate(conn, *, account_id, intents) -> GateResult`
    (approved/blocked/rescaled intents + `kill_switch_reasons`);
  - `submit_book_intents(conn, *, book_id, account_id, intents, broker, gate, fee, on_fill=None)`
    that: runs `gate.evaluate(...)` → for each approved intent, `broker.place_order` → persist to
    clean `orders` (`OrderRepository.insert`, status from the broker) + `order_fills` on fill →
    on `FILLED`, update `positions` (`PositionRepository.upsert`) and append a `ledger` entry
    (`LedgerRepository.insert`, `entry_type='trade'`, `reference_type='order'`,
    `reference_id=<order_id>`). Broker-API exceptions → append the broker-anomaly kill-switch reason
    and stop, mirroring today's behavior.
- **No caller wired yet.** Full unit tests with a `FakeBroker`: happy fill, no-fill/hold, partial,
  broker-exception → anomaly, gate-blocked → nothing submitted.
- Check: `run_suite src/trading/services/execution` green; layer + mypy clean.

### Phase 2a-2 — Pre-submit gate policy (kill switches as an injected gate)  **[strong]**
- Implement a `PreSubmitGate` that composes today's checks: the stale-price, reconciliation
  mismatch/staleness/missing, and broker-anomaly kill switches (from `runtime.py` +
  `sleeves/risk_gate.py` + `sleeves/reconciliation.py`), plus the domain risk-gate
  (`evaluate_sleeve_risk_gate`, allow/rescale/block). Reuse the existing domain policy + config; this
  phase only relocates orchestration into a gate object.
- Persist the risk snapshot/decisions through the existing repos (unchanged records) so the audit
  trail is preserved.
- Check: gate unit tests (each kill switch fires; allow/rescale/block honored) green.

### Phase 2a-3 — Route account mode through the service  **[strong]**
- In `auto_trading/runtime.py`, replace `_broker_aware_record_trade` with a call to
  `submit_book_intents` against the account's **default book** (resolve via `book_bridge`), passing
  the injected gate. The account's selection tuple becomes a single-book `BookTradeIntent`.
- Account mode now writes the clean tables **and** inherits the kill switches (safety strengthens).
- Check: `run_suite src/trading/services/auto_trading` green (update account-mode submission tests to
  assert clean-table writes).

### Phase 2a-4 — Route sleeve mode through the service + move reconciliation  **[strong]**
- Replace the inline loop in `_run_sleeve_mode_for_account` with per-book `submit_book_intents`
  calls; the sleeve risk gate becomes the injected gate. `SleeveTradeIntent` maps to
  `BookTradeIntent` (sleeve → its bridging book).
- **Reconciliation dependency:** `reconcile_open_broker_orders` reads `broker_orders`/`sleeve_orders`
  today. Move it to read the clean `orders`/`order_fills` in the same phase (it must not be left
  reading tables the submission path no longer writes).
- Check: `run_suite src/trading/services/auto_trading src/trading/services/sleeves` green.

### Phase 2a-5 — Retire legacy submission writers  **[strong]**
- Remove `_broker_aware_record_trade`, the inline sleeve persistence, and the now-unused
  `SleeveOrderRepository`/`sleeve_fills` write paths. Confirm no reader remains for
  `sleeve_orders`/`sleeve_fills`/`broker_orders` on the submission/reconciliation path.
- **Table drops are a separate, final cleanup** — only after a repo-wide search proves nothing reads
  them (mind reporting/CSV export/admin deletions). Stage the DROPs like the P3 E-phase cutovers
  (drop empty/legacy tables, note the pre-P4 backup).
- Check: full `run_checks ci` green.

## 7. Areas of code expected to be edited
- **New:** the `trading.services.execution` package (service + gate + intent contract), with tests under
  the mirrored `execution` test suite.
- `src/trading/services/auto_trading/runtime.py` — account + sleeve submission call sites;
  reconciliation re-point.
- `src/trading/services/sleeves/` — risk-gate reuse into the injected gate; retire the inline
  submission persistence.
- `src/trading/repositories/` — clean `orders`/`order_fills`/`positions`/`ledger` writers already
  exist (P3 Phase C); `book_bridge` resolves account/sleeve → book.
- Reconciliation (`auto_trading/runtime_reconciliation.py`) — read clean `orders`.

## 8. Validation
```
.venv\Scripts\python.exe -m scripts.checks.run_suite src/trading/services/execution src/trading/services/auto_trading src/trading/services/sleeves --no-cov
.venv\Scripts\python.exe -m scripts.checks.repo.layer_check
.venv\Scripts\python.exe -m scripts.checks.python.mypy_check
.venv\Scripts\python.exe -m scripts.run_checks ci      # final, per phase where feasible
```
Add execution-service tests (fake broker: fill / hold / partial / broker-exception / gate-blocked)
and cutover tests asserting the clean tables receive the writes.

## 9. Failure handling
- A kill switch would be weakened or dropped to ease merging → **stop**; the stricter guard wins.
- Reconciliation can't be re-pointed without also moving a writer → sequence them in the same phase;
  do not leave reconciliation reading an abandoned table.
- A legacy table still has a live reader at drop time → do **not** drop it; leave it and record the
  remaining reader as a follow-up.
- Any check red → fix or stop and report; never commit on red.

## 10. Out of scope (this work order's 2a focus)
- **2c (unified accounting/ledger):** make sleeve fills a clean extension of the single ledger path
  rather than a divergent `record_trade` copy. Follows 2a; detail when reached.
- **2b (unified rotation/selection):** collapse account-episode + champion/challenger onto the
  decision-score contract; reduce rotation module sprawl; retire the episode path. Depends on 1a
  (done). P5 naming pass alongside.
- Broker adapters / environment axis (already converged behind the `BrokerConnection` port).

## 11. Final report (per `AGENTS.md`)
- **Developer verification:** run a paper account (default-book) and a sleeved account through the
  daily job; confirm orders/fills/positions/ledger land in the **clean** book-keyed tables and the
  kill switches fire for both modes.
- **Validation run:** §8 commands + results.
- **Cleanup notes:** legacy submission writers removed; legacy tables dropped (or the remaining
  reader that blocked a drop).
