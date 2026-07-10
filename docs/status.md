# Status - What Is Left

Type: notes
Status: Active
Created: 2026-07-08
Last Reviewed: 2026-07-09
Purpose: Current status summary for remaining committed work and deferred independent workstreams.
Related: [Overview](overview.md)

Completed phase detail lives in git history and durable decisions live in [ADRs](adr/).

## Remaining committed work

### Deploy step pending - sleeve retirement DB migration

The sleeve retirement (SR-1...SR-7) is **code-complete**; one operator step remains when the
`features/sleeve-retirement` branch deploys to a host with an existing DB. Full procedure
(backup -> run the one-time data-op -> verify -> drop the four orphaned tables -> delete the
migration tooling): **[runbooks/sleeve-retirement-db-migration.md](runbooks/sleeve-retirement-db-migration.md)**.
Fresh DBs need nothing.

## Deferred independent work

| Workstream | Why deferred | Trigger to revisit |
|---|---|---|
| P6 - Plug-and-play strategy catalog | Catalog rows exist, but wiring them now duplicates the code registry before there is demand | Concrete demand to add or tune strategy variants without deploys |
| P10 - Adaptive learning | Design-heavy and not yet proven to beat the static decision score | Evidence that a learned layer improves decisions |
| P11 - Parameter optimization | Requires catalog-backed variants and explicit overfitting guardrails | Demand for systematic parameter sweeps |
| P12 - Backtest freshness cadence | Policy question, not current implementation pressure | Evidence that stale backtests skew rotation or promotion |
| Execution-mode collapse | Changes account-mode compatibility semantics after sleeve retirement | Runtime mode handling is next touched |

## Dropped (do not silently re-add)

- **Trends workflow integration into API/UI** - `apps/trends/` stays a standalone CLI.
- **Non-proxy alternative-data expansion** - ETF-proxy feature providers are sufficient for now.
- **Native `IbApiClient` socket path** - the Client Portal / Web API client is the active IBKR
  integration; the legacy socket path stays documented stubs only.
