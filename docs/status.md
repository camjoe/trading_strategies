# Status

Type: status
Status: Active
Created: 2026-07-08
Last changed: 2026-07-08
Purpose: The single source of truth for **current** status — what is done, active, blocked, or
deferred, and the next action for each. Current truth only; no progress narrative.
Related: [Overview](overview.md) (north star / why), [Decisions](decisions.md) (ADR-style records),
[Docs History](history/README.md) (completed work + progress logs).

> **Read this for "what now."** Rationale and product framing are in [overview.md](overview.md);
> resolved decisions in [decisions.md](decisions.md); finished work and its narrative in
> [history/](history/README.md). Detailed change history is in git — do not re-log it here.
>
> **Type** ∈ feature · refactor · cleanup · migration · docs · exploratory.
> **Status** ∈ not started · in progress · blocked · deferred · done.

## Active

| Workstream | Type | Status | Depends On | Decision Needed | Next Action |
|---|---|---|---|---|---|
| Unified parameter source (P7) | feature | not started | P3 ✅ | none (D4 settled the store; scope the operator use case) | Scope the concrete operator use case first (avoid speculative surface); then a read/edit service + CLI over the existing ~5 param stores. |
| Portfolio risk rollup (P9) | feature | not started | equity snapshots ✅ | [D10](decisions.md#d10) — only for the concentration slice | Build the v1 exposure rollup (read-only cross-account equity/cash/market-value); overlap/concentration follows once D10 lands. |
| Retire/rename sleeve vocabulary | cleanup/refactor | not started | P4 ✅ | Are sleeves still a distinct concept from books, or just legacy naming? | Write an ADR answering that; then rename `services/sleeves/*` + `strategy_sleeves` accordingly. Distinct from P4 book accounting, which is **done**. |

## Exploratory

Pursued only if evidence justifies. Not on the committed path.

| Workstream | Type | Status | Depends On | Decision Needed | Next Action |
|---|---|---|---|---|---|
| Plug-and-play strategy & provider catalog (P6) | exploratory | deferred | P1 ✅ · P3 ✅ | Concrete demand to run data-defined strategy variants (needs a write path too)? | None until demand. Then go all the way: DB catalog canonical, retire `STRATEGY_REGISTRY` to primitives — not a loader alongside the code registry. |
| Adaptive learning (P10) | exploratory | deferred | decision-score contract ✅ | [D9](decisions.md#d9) — what learned state is + update policy | None until D9 + evidence. |
| Strategy parameter optimization (P11) | exploratory | deferred | — | [D11](decisions.md#d11) — search method + overfitting guardrails | None until D11 + evidence. |
| Backtest freshness / recalculation cadence (P12) | exploratory | deferred | — | Freshness/staleness policy for re-running backtests | None until demand. |

## Recently completed

Compact record only; detail is in git and [history/](history/README.md).

| Workstream | Delivered |
|---|---|
| Close the execution loop (P1) | 2026-07-03 |
| Unified evaluation — decision-score contract (P2) | 2026-07-04 |
| DB schema rewrite — clean book schema (P3) | 2026-07-05 |
| Converge accounts & sleeves — submission/rotation/accounting (P4) | 2026-07-07 |
| Decisioning naming pass — `Rotation*` rename (P5, with 2b-5) | 2026-07-07 |
| Email notifications — webhook + SMTP (P8; per-transport filtering deferred) | 2026-07-07 |

## Dropped

Recorded so they are not silently re-added without a fresh decision.

- **Trends workflow integration into API/UI** — `apps/trends/` stays a standalone CLI.
- **Non-proxy alternative-data expansion** — ETF-proxy feature providers are sufficient for now.
- **Native `IbApiClient` socket path** — the Client Portal / Web API client is the active IBKR
  integration; the legacy socket path stays documented stubs only.
