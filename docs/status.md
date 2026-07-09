# Status — What Is Left

Type: notes
Status: Active
Created: 2026-07-08
Last changed: 2026-07-08
Last Reviewed: 2026-07-08
Purpose: The single source of truth for what remains of the plan — what is left, the steps to
complete it, and what is deferred. Current truth only; completed work lives in git history.
Related: [Overview](overview.md) (north star / why), [Decisions](decisions.md) (decision records).

> The original 11-phase plan (P1–P11, later P12) is more than half delivered: **P1–P5 and P8 are
> done** (see the compact table at the bottom; details are in git). What follows is everything
> that remains.
>
> **Type** ∈ feature · refactor · cleanup · exploratory. **Status** ∈ not started · in progress ·
> blocked · deferred.

## Remaining committed work

The two committed workstreams are **independent of each other** — either can be done first, or both
in parallel.

### P7 — Unified parameter source (feature · not started)

One legible place to view/edit the parameters that drive strategy behavior, evaluation, and
rotation. Today they are scattered across ~5 stores (`strategy_param_sets`, `operational_settings`,
`RotationPolicyConfig` code defaults, account profiles JSON, account/book DB columns).

Steps:
1. Scope the concrete operator use case first — which parameters actually need runtime tuning
   (avoid speculative surface; the P6 lesson).
2. Build a read-through view service over the existing stores (no new store — D4 already decided
   where params live).
3. Add the CLI to view/edit through that service (interface primacy: CLI first, UI optional later).
4. Migrate rotation/evaluation weights that should be tunable out of code-only defaults.

### P9 — Portfolio risk rollup (feature · not started)

Cross-account risk visibility from data that already exists.

Steps:
1. **v1 exposure rollup**: aggregation service over `equity_snapshots` + positions returning
   cross-account equity, cash, and market value. Read-only, low risk.
2. CLI entry for the rollup payload.
3. **Overlap/concentration** (second slice): needs [D10](decisions.md#d10) first — define
   concentration (by symbol, sector, or strategy) — then symbol-level cross-account analysis.
4. Optional dashboard view only after the payload contract is stable.

### Deploy step pending — sleeve retirement DB migration (migration · blocked on operator)

The sleeve retirement (SR-1…SR-7) is **code-complete**; one operator step remains when the
`features/sleeve-retirement` branch deploys to a host with an existing DB. Full procedure
(backup → run the one-time data-op → verify → drop the four orphaned tables → delete the
migration tooling): **[runbooks/sleeve-retirement-db-migration.md](runbooks/sleeve-retirement-db-migration.md)**.
Fresh DBs need nothing.

## Deferred (exploratory — only if evidence justifies)

| Workstream | Why deferred | Trigger to revisit |
|---|---|---|
| P6 — Plug-and-play strategy catalog | DB catalog exists but wiring it now duplicates the code registry for no gain | Concrete demand to add/tune strategy variants without deploys; then make DB canonical + retire `STRATEGY_REGISTRY` to primitives |
| P10 — Adaptive learning | Design-heavy; needs [D9](decisions.md#d9) | Evidence that a learned layer beats the static decision score |
| P11 — Parameter optimization | Needs [D11](decisions.md#d11) (search method + overfitting guardrails) | Demand for systematic param sweeps |
| P12 — Backtest freshness cadence | Policy question, not implementation | Evidence that stale backtests are skewing rotation decisions |
| Execution-mode collapse (one mode: trade every assigned book; account mode = default book) | Deferred during the sleeve retirement — changes account-mode strategy/state resolution semantics | When touching runtime mode handling next; sleeves are gone so the collapse is a clean refactor |

## Done (compact record — details in git)

| Phase | Delivered |
|---|---|
| P1 — Close the execution loop | 2026-07-03 |
| P2 — Unified evaluation (decision-score contract) | 2026-07-04 |
| P3 — DB schema rewrite (clean book schema) | 2026-07-05 |
| P4 — Converge accounts & sleeves (submission/rotation/accounting) | 2026-07-07 |
| P5 — Decisioning naming pass (`Rotation*` rename) | 2026-07-07 |
| P8 — Email notifications (webhook + SMTP; per-transport filtering deferred) | 2026-07-07 |
| Sleeve retirement — sleeves removed; accounts + books are the one flow (fixed two live staleness bugs: rotation assignment drift, w3 allocation drift; ADR 003 superseded) | 2026-07-09 |

## Dropped (do not silently re-add)

- **Trends workflow integration into API/UI** — `apps/trends/` stays a standalone CLI.
- **Non-proxy alternative-data expansion** — ETF-proxy feature providers are sufficient for now.
- **Native `IbApiClient` socket path** — the Client Portal / Web API client is the active IBKR
  integration; the legacy socket path stays documented stubs only.
