# Service Ownership Map

Type: architecture
Status: Active
Created: 2026-07-22
Last Reviewed: 2026-08-13
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
| `execution/` | The full **order lifecycle**: `selection/` (what to trade), `ledger/` (trade/cash accounting), `submission`, pre-submit `gate`/`pre_submit_gate`, `risk`, `nav`, `equity_reconciliation`, `open_order_reconciliation`. | Rotation policy → `books/rotation/`. Presentation → `reporting/`. |
| `books/` | The **execution primitive**: book state (`book_assignments`, `sector_config`, `helpers`) plus the `rotation/` sub-package. | Intent generation → `execution/selection/`. Daily report assembly → `analysis/daily_report.py`. |
| `evaluation/` | Strategy **evidence + decision-score math**. | Report formatting → `reporting/`. Portfolio analytics → `analysis/`. |
| `analysis/` | Portfolio/benchmark/performance/risk-snapshot/**concentration/exposure analytics math**. | Presentation → `reporting/`. |
| `reporting/` | **Composite** operator reports — printed output that composes several packages or all accounts (account report, strategy comparison, concentration/exposure rollups), as thin views over `analysis`/`evaluation`. | Any analytics or evaluation **math** → `analysis`/`evaluation`. Single-package display → that package's own `presentation.py` (see [Presentation ownership](#presentation-ownership)). |
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
(`backtesting.services`), not a service here.

## Internal layouts worth calling out

`execution/` and `books/` are subdivided only where a directory otherwise forces a reader to
guess which concern a file belongs to.

```
execution/
  selection/   # selection.py (signal selection/sizing) + book_intents.py (book-keyed intents)
  ledger/      # mutations.py + queries.py (trade/cash accounting)
  gate.py  pre_submit_gate.py  risk.py  submission.py  nav.py
  equity_reconciliation.py  open_order_reconciliation.py  constants.py

books/
  book_assignments.py  sector_config.py  helpers.py   # book state
  rotation/
    engine.py  metrics.py  challenger_evaluation.py  config_parser.py
```

## Presentation ownership

Operator-facing display splits by whether it presents one package's own data or composes several:

- **Single-package display** — presenting a payload a package owns (a `PromotionAssessment`, a
  `ParameterSourceView`, a settings-change trail, an account listing) — lives in that package's
  `presentation.py`, with the `show_*`/`render_*` entrypoint exposed on the package `__init__`.
- **Composite / cross-package reports** — output that composes multiple packages or all accounts
  (the account report, strategy comparison, concentration/exposure rollups) — lives in `reporting/`,
  which owns no domain of its own and stays a thin view over `analysis`/`evaluation`.

Rule of thumb: if the formatter reaches into more than one service's data, it is a report and belongs
in `reporting/`; if it renders one package's own payload, it stays with that package. A display helper
shared by both a package and `reporting/` (e.g. `evaluation.presentation.backtest_freshness_display_parts`)
belongs to the package that owns the concept, not to `reporting/`.

## Why the boundaries pay off

Consolidating a concept into one owner turns several change surfaces into one: a changed
requirement is implemented once (not three times), duplication becomes visible and removable,
and divergent-fix bugs disappear. This is strongest where a service has genuine shared behavior
(`execution/`, `books/rotation/`); it is not a reason to merge already-cohesive services.

## Facades

Import from the concrete module that owns a symbol; do not add a re-export `__init__` facade.
`execution` and `books` are the model. The service packages once carried `__all__` facades from
an earlier convention; all are now retired.
