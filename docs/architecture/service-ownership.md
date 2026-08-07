# Service Ownership Map

Type: architecture
Status: Active
Created: 2026-07-22
Last Reviewed: 2026-07-22
Purpose: State the ownership boundary of each `src/trading/services/` package — what it owns and, just as importantly, what it does **not** own — so new code lands in the one service that owns the concept.
Related: [Architecture Conventions](architecture-conventions.md), [Service Cookbook](service-cookbook.md), [Trading Package Map](../maps/trading-package-map.md)

## Scope

`architecture-conventions.md` owns the **layer-level** ownership (interfaces → services →
repositories/domain → models). This doc is finer-grained: the boundaries **between service
packages** inside `src/trading/services/`. When a change spans two services, this table decides
where it goes.

## Ownership table

| Service | Owns | Does **not** own (goes elsewhere) |
|---|---|---|
| `auto_trading/` | Scheduled paper/live run **orchestration** only (`inputs`, `market`, `runtime`). | Order selection, submission, reconciliation, risk → `execution/`. |
| `execution/` | The full **order lifecycle**: `selection/` (what to trade), `ledger/` (trade/cash accounting), `submission`, pre-submit `gate`/`pre_submit_gate`, `risk`, `nav`, `reconciliation`, `open_order_reconciliation`. | Rotation policy → `books/rotation/`. Presentation → `reporting/`. |
| `books/` | The **execution primitive**: book state (`book_assignments`, `sector_config`, `helpers`) plus the `rotation/` sub-package. | Intent generation → `execution/selection/`. Daily report assembly → `analysis/daily_report.py`. |
| `evaluation/` | Strategy **evidence + decision-score math**. | Report formatting → `reporting/`. Portfolio analytics → `analysis/`. |
| `analysis/` | Portfolio/benchmark/performance/risk-snapshot/**concentration/exposure analytics math**. | Presentation → `reporting/`. |
| `reporting/` | **Read-only presentation** payloads and printed operator output (thin views over `analysis`/`evaluation`). | Any analytics or evaluation **math** — it stays in `analysis`/`evaluation`. |
| `promotion/` | Human-gated promotion review workflow + its CLI rendering. | Evidence/score math → `evaluation/`. |
| `accounts/` | Broker-account identity/custody/metadata, listing, config, and deletions. | Book-level execution/accounting → `execution/`. |
| `operational_settings/` | Global operator settings (throttles, evaluation confidence, promotion policy) + throttle **enforcement**. | Per-book settings → `books`. It stays **separate** from `parameters/`. |
| `parameters/` | A read/edit **surface** over the owning stores (global settings, book settings, strategy rows). | It is **not** a persistence owner — writes go to the owning store. |
| `universe/` | Expands universe names into ticker lists for the write paths; owns the default-universe vocabulary. | Nothing here runs on the trading path — books store resolved symbols. |
| `market_data/` | Market-data ports/factory, proxy feature computation, and caller-facing price/benchmark `lookups`. | Concrete adapters → `src/infrastructure/market_data/`. |
| `strategy_catalog/` | Strategy primitive + `params_json` resolution and catalog edits. | — |
| `universe/` | Trade-universe resolution. | — |
| `autonomy_monitor/` | Autonomy / paper-account operator monitoring (artifacts, queries). | — |
| `fixtures/` | Deterministic synthetic data seeding for generated databases (the offline demo story and the sandbox test bed). | Does not own production writes — it drives the owning service for every derived record. |

Stale-backtest remediation lives in the backtesting bounded context
(`trading.backtesting.services`), not a service here.

## Internal layouts worth calling out

`execution/` and `books/` are subdivided only where a directory otherwise forces a reader to
guess which concern a file belongs to.

```
execution/
  selection/   # selection.py (signal selection/sizing) + book_intents.py (book-keyed intents)
  ledger/      # mutations.py + queries.py (trade/cash accounting)
  gate.py  pre_submit_gate.py  risk.py  submission.py  nav.py
  reconciliation.py  open_order_reconciliation.py  constants.py

books/
  book_assignments.py  sector_config.py  helpers.py   # book state
  rotation/
    engine.py  metrics.py  challenger_evaluation.py  config_parser.py
```

## Why the boundaries pay off

Consolidating a concept into one owner turns several change surfaces into one: a changed
requirement is implemented once (not three times), duplication becomes visible and removable,
and divergent-fix bugs disappear. This is strongest where a service has genuine shared behavior
(`execution/`, `books/rotation/`); it is not a reason to merge already-cohesive services.

## Facades

A package `__init__` that re-exports its public surface is permitted **only** as a deliberate,
consumed public entrypoint (e.g. `execution/ledger`, `accounts`, `market_data`). Do not add a
re-export `__init__` that nothing imports; prefer direct imports from the concrete module.
