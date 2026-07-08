# Implementation Guide — P4: Converge accounts & sleeves on the clean book schema

Type: implementation
Status: Active - 2a + 2c + 2b complete (2026-07-07); P4 substantively done — see §0 Status
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

## 0. Status (2026-07-07)

P4 is substantively complete. All three sub-features landed on the clean book schema:

| Sub-feature | State | Where |
|---|---|---|
| **2a** — shared order-submission service (2a-1…2a-5) + sleeve-migration cleanup | ✅ done | this doc §6 |
| **2c** — unified book accounting (2c-1…2c-4) | ✅ done | this doc §6b |
| **2b** — unified rotation/selection (2b-1…2b-4, 2b-6, 2b-7) | ✅ done | [P4/2b work order](p4-2b-unified-rotation.md) |

**Left to do (P4):** the `Rotation*` **naming pass** (deferred; convention + rename table in the 2b work
order §Phase 2b-5), and one **open decision** — backtest recalculation cadence (2b work order §"Open
decision"). Both are optional / low-urgency.

**Later initiatives (out of P4 scope):** **P5** = the naming pass proper; **P7** = unified
parameter-source cleanup (param sprawl across stores — e.g. `min_trades` in
`generate_sleeve_trade_intents`). Prior phases: **P1** execution loop (Complete), **P3** DB schema
rewrite (Complete), **P2** evaluation contract tests (see its doc).

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

> **Sequencing refined 2026-07-05 (during 2a-3).** 2a splits into an *isolated build* (2a-1 service +
> 2a-2 gate, no caller — done) and a *cutover* (2a-3 account, 2a-4 sleeve, 2a-5 retire). The cutover
> is **blocked on 2c**: the gate's reconciliation kill switch and notional caps read
> `books.current_equity`, which is bootstrapped to `initial_cash` and **never maintained during 2a**,
> while the snapshot it reconciles against is market-marked (`account_report`). So the live order is
> **2a-1/2a-2 → 2c → 2a-3/2a-4/2a-5 → 2b**. See §5 and the 2c build plan (§6b).

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
- **Gate risk bucket = book (book-as-bucket):** the pre-submit gate reuses the domain notional
  risk-gate policy (`evaluate_sleeve_risk_gate`) **unchanged** by treating `book_id` as the risk
  bucket (a sleeve is one book; a plain account is one default book) and adapting book
  intents/equity/positions into the policy's sleeve-shaped inputs. Account mode therefore also gains
  the notional caps — a strengthening beyond the DoD minimum, consistent with "safety only
  strengthens". *(Decided 2026-07-05, during 2a-2.)*
- **2c is sequenced before the 2a cutover:** the gate needs live, market-marked book equity to run on
  the account/sleeve path (reconciliation kill switch + notional caps). Book balances aren't
  maintained until 2c, so 2c lands first. *(Decided 2026-07-05, during 2a-3 — see §6b.)*
- **Greenfield reset at cutover:** the clean book tables have no history (2a-1 is their first writer),
  so an existing account's book equity (≈ `initial_cash`, no positions) can't reconcile against a
  snapshot reflecting full trade history. Per P3's greenfield stance, the cutover starts fresh — book
  and snapshot both begin empty and reconcile cleanly; pre-cutover history is not backfilled.
  *(Decided 2026-07-05, during 2a-3.)*
- **Reconciliation is per-run, not per-trade:** account mode selects/fills trades one at a time in a
  loop, so after a fill book equity drifts from the snapshot by the fee. The equity-reconciliation
  kill switch therefore runs **once pre-flight** (NAV-mark → reconcile → hold the whole run on a
  mismatch); the per-trade gate uses `reconcile=False` and keeps only stale-price + notional caps.
  *(Decided 2026-07-05, during 2a-3.)*

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

### Phase 2a-3 — Route account mode through the service  **[strong]**  *(done)*
> **2c prerequisite met.** Implemented on the cutover branch: `run_for_account` NAV-marks the account's
> books and runs the equity-reconciliation kill switch **once pre-flight** (holds the run on a
> mismatch; greenfield keeps fresh accounts aligned); each selected trade routes through
> `submit_book_intents` with `BookPreSubmitGate(reconcile=False)` (stale-price + notional caps), and
> `on_fill` bridges to `record_trade` so the legacy account ledger stays in sync. Legacy
> `broker_orders` writes are dropped for account mode — open-order reconciliation re-points to clean
> `orders` in 2a-4 (a no-op for paper, which fills synchronously).
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

## 6b. Build plan — 2c (unified accounting; sequenced before the 2a cutover)

**Why now:** the gate (2a-2) reads `books.current_equity` for its reconciliation kill switch and
notional caps, but book balances are bootstrapped to `initial_cash` and never maintained during 2a,
and the snapshot the reconciliation compares against is **market-marked** (`account_report` via a
provider). 2c makes the book ledger the single accounting source, maintains book balances on fills,
and marks book NAV to market — so the gate has valid data when 2a-3/2a-4 wire it.

**Current divergence (evidence):** accounts use `record_trade` → `trades` (equity market-marked at
report time); sleeves use `apply_sleeve_fill` → `sleeve_ledger` + `sleeve_positions` +
`strategy_sleeves` balances (fill-marked); the clean path (2a-1) writes `positions` + a single
minimal `trade` ledger entry and no book balances.

### Definition of Done (2c)
- [ ] `submit_book_intents` on-fill writes the full book `ledger` split (cash movement + fee +
      realized-pnl) and maintains `books.current_cash`/`current_equity`, reusing the domain fill
      transition; exec-id idempotency preserved.
- [ ] A book NAV-marking service marks a book's positions to current provider prices and updates
      `current_equity`, mirroring the sleeve NAV marking the runtime snapshot/reconciliation relies on.
- [ ] Book equity reconciliation (NAV-marked book equity vs latest snapshot) is the valid source the
      gate's reconciliation kill switch consumes.
- [ ] Sleeve fills are a clean extension of the single book-ledger path — no divergent `record_trade`
      / `sleeve_ledger` copy on the converged path (legacy writers retire in 2a-5).

### Phase 2c-1 — Book fill accounting: ledger split + book balances, in isolation  **[strong]**
- Extend the 2a-1 on-fill into a **summable cash-flow ledger** using the clean `ledger` vocab.
  **Correction (found during 2c-1):** the `ledger.entry_type` CHECK allows only
  `trade`/`fee`/`deposit`/`withdrawal`/`adjustment` — the sleeve ledger's `cash_movement`/`realized_pnl`
  are **not** valid here, so don't port them. Instead write a `trade` entry for gross cash
  (buy `-(qty×price)`, sell `+(qty×price)`) plus a `fee` entry (`-(commission+fee)`) when non-zero,
  both `reference_type='order'`, `reference_id=<order_id>`; the two sum to the net cash delta.
  Realized P&L is **not** a cash-ledger entry (it's derived for reporting) — a deliberate cleanup vs
  the sleeve ledger's mixed audit design.
- Update `books.current_cash` (authoritative, `+= cash_delta`) and `current_equity` (fill-marked:
  `cash + Σ position market value`) via `BookRepository.update_balances`. Reuse
  `apply_sleeve_fill_transition` for the position/cash math. Fill exec-id idempotency (`order_fills`)
  preserved.
- **No caller change.** Tests: buy/sell ledger rows sum to cash delta; book cash/equity updated; fee
  splits into its own entry; equity drops by the fee.
- Check: `run_suite src/trading/services/execution` green; layer + mypy clean.

### Phase 2c-2 — Book NAV-marking service  **[strong]**
- A service that, given current prices, marks a book's (or an account's books') `positions` to market
  and recomputes `current_equity = current_cash + Σ(qty × price)`, updating `books`. Mirrors the
  sleeve NAV marking (`01_mark_sleeve_nav` is handled inside the runtime snapshot/reconciliation).
- Check: NAV-marking unit tests (equity reflects marked prices; missing price handled).

### Phase 2c-3 — Book equity reconciliation as the gate's source  **[strong]**
- Reconcile Σ(book equity) (NAV-marked) vs the latest account snapshot within tolerance. The runtime
  marks books (2c-2) before invoking the gate so the reconciliation kill switch reads valid equity.
- Check: reconciliation unit tests (within/out-of-tolerance; stale/missing snapshot).

### Phase 2c-4 — Confirm the snapshot ↔ book-equity roll-up  **[light]**
- **Correction (found during 2c-4):** do **not** point the reconciliation snapshot at book balances.
  The reconciliation kill switch compares Σ book equity against the snapshot; if the snapshot were
  *derived from* those same book balances, both sides share one source and the check becomes a
  tautology — a weakened kill switch. The snapshot must stay an **independent** measure. During the
  migration that independent measure is the account/trades roll-up (`account_report`); post-migration
  it becomes the **broker** (`get_account_info`) — see the follow-up below.
- So 2c-4 is the plan's *confirm* option: prove that the clean book accounting and the independent
  account/trades accounting **agree** on the same fills marked at the same prices, so the
  reconciliation won't false-positive at cutover.
- Check: an integration test runs one fill through both paths (`record_trade` + `submit_book_intents`),
  marks at shared prices, and asserts equal equity + a clean `reconcile_book_equity` against the
  account-sourced snapshot.
- **Follow-up (post-cutover, not 2c):** once the legacy trades path retires (2a-5), the reconciliation
  snapshot must move to the broker's reported equity (book-vs-reality), since book-vs-trades no longer
  has two independent sources. Track under the reconciliation redesign.

After 2c: resume **2a-3 → 2a-4 → 2a-5** with the now-valid gate, then **2b**.

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
- **2c (unified accounting/ledger):** now detailed in §6b and sequenced **before** the 2a cutover —
  make sleeve/account fills a clean extension of the single book-ledger path (no divergent
  `record_trade` copy), maintain book balances, and mark book NAV to market for reconciliation.
- **2b (unified rotation/selection):** now detailed in its own work order —
  [p4-2b-unified-rotation.md](p4-2b-unified-rotation.md). Collapse account-episode + champion/challenger
  onto the decision-score contract, book-keyed; retire the (unused) regime/overlay subsystem + the
  episode path; reduce rotation module sprawl; P5 naming pass alongside. *(Direction confirmed
  2026-07-07: full collapse — regime/overlays are provably unused.)*
- Broker adapters / environment axis (already converged behind the `BrokerConnection` port).

## 11. Final report (per `AGENTS.md`)
- **Developer verification:** run a paper account (default-book) and a sleeved account through the
  daily job; confirm orders/fills/positions/ledger land in the **clean** book-keyed tables and the
  kill switches fire for both modes.
- **Validation run:** §8 commands + results.
- **Cleanup notes:** legacy submission writers removed; legacy tables dropped (or the remaining
  reader that blocked a drop).
