# Project Overview

Type: overview
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-08-02
Purpose: Explain the project's current capabilities, concepts, architecture, limitations, and scope.
Related: [Architecture Conventions](architecture/architecture-conventions.md), [Docs Index](README.md)

## What this app is

A research framework for developing, backtesting, and paper-trading quantitative strategies. It
supports historical backtesting and walk-forward optimization, simulated execution, strategy
comparison, and human-reviewed promotion workflows. Broker-connected and live-trading paths are advanced,
experimental surfaces protected by explicit safety gates.

## Core concepts (glossary)

- **Account** — the broker/custody entity. Owns the broker connection, the `live_trading_enabled`
  safety gate, and account-wide identity/metadata. Books own execution cash, positions, and settings;
  account views roll those book records up. A "test" account is just an account with `broker_type="paper"`.
- **Book** — the execution primitive: a bounded pool of capital inside an account run to one
  strategy; one broker account can host several independent books.
- **Strategy** — a named signal specification (`StrategySpec`) with a signal function and default
  parameters across trend, mean-reversion, oscillator, breakout, and external-data
  ("alternative") families.
- **Strategy knobs** — tunable parameters for a strategy primitive. Resolved at runtime from the
  `strategies` catalog row: the primitive's code defaults with the row's `params_json` layered
  on top.
- **Evaluation** — the canonical `StrategyEvaluationArtifact`: backtest + walk-forward + paper/live
  evidence fused into confidence and a blended decision score.
- **Rotation** — book-keyed switching of the active strategy through a champion/challenger policy
  using the decision-score contract. For a live-trading account, a challenger must have an approved
  promotion review before it is eligible to be rotated in; paper accounts rotate unrestricted, since
  that is how promotion evidence gets gathered.
- **Promotion** — the human-gated lifecycle (research → paper → live-review) with audit history.
- **Feature provider** — an external-data source (news, social, policy/ETF-proxy) that influences
  *trade signals* for "alternative" strategies. Feature providers are signal inputs, not evaluation
  evidence: their effect reaches evaluation only through realized paper/live P&L.
- **Broker / environment** — paper simulator, IBKR Web API, or IBKR socket API, all behind one
  `BrokerConnection` port and factory. Paper vs. IBKR-paper vs. live differ by adapter + the
  `live_trading_enabled` guard, not by separate code paths.

## What it can do today

- **Multi-strategy backtesting and walk-forward optimization** (`backtest-optimize`) that run the
  real strategy signal functions, persist completed result trees atomically, distinguish run
  purpose, and derive experiment/window summaries from member runs. See
  [ADR 016](adr/016-optimizer-experiments-as-research-evidence.md) for how optimizer experiments
  count as research evidence.
- **Canonical evaluation** (`src/trading/services/evaluation/`) fusing backtest, walk-forward, and
  paper/live evidence into confidence + a blended score, exposed through one decision-score contract
  (`EvaluationDecisionScore`).
- **Promotion workflow** with research/paper/live-review stages, a human gate, stable strategy identity,
  conditional single-close behavior, and chronological event history.
- **Signal-driven paper and broker-connected execution** — selection evaluates the active strategy's signal function
  per candidate ticker through the same `evaluate_signal(...)` entry the backtester uses: trade only
  on real signals, no forced minimum, a per-run max cap. Rotation changes what the trader actually
  does.
- **Paper trading** with equity snapshots, trades, and benchmark overlays.
- **Multi-book accounts** — one broker account hosting multiple strategy books, with
  champion/challenger rotation, a pre-submit risk gate + kill switches, and equity reconciliation.
- **Broker abstraction** — paper, IBKR Web API, and IBKR socket adapters behind one
  port + factory, with a hard `live_trading_enabled` safety guard.
- **Feature providers** — news, social, and policy (ETF-proxy) sources. Only the policy provider
  reaches a decision today, as the regime input to rotation's regime-fit component
  (`services/books/rotation/metrics.py`). News and social are probed by the UI features tab but feed
  no strategy: feature-driven signals are deferred, not broken. See
  [Built but not wired up](#built-but-not-wired-up).
- **Runtime scheduler jobs** (challenger shadow evaluation, governance,
  health checks, reporting) plus a **CLI** and an optional **web UI** (`apps/paper_trading_web`).
- **Operational settings** (evaluation confidence, promotion policy, trade throttles) and
  **account profiles** for configuration, plus a **unified parameter source**: one `parameters`
  view over every store with `configure-*` CLI edits for global settings and per-book rotation
  policy.
- **Data-defined strategy variants**: the `strategies` catalog is the canonical runtime source
  for strategy definitions and knobs; operators add and tune variants via `create-strategy-variant`,
  `configure-strategy`, and `freeze-strategy` without a deploy.
- **Cross-account portfolio risk rollup**: exposure, symbol concentration/overlap, and sector
  rollup via CLI, API, and a read-only Portfolio UI tab.

## Built but not wired up

Code that exists, passes tests, and is *not* reached by any CLI command, runtime job, or API route.
Listed because it reads as working capability from the inside and as dead code from the outside, and
is neither. Established by tracing every entrypoint (2026-08-09); re-derive rather than trust this
list if it has aged.

- **Feature-driven strategies are deferred by decision.** Signals reading external features were
  scoped and put on hold; the provider implementations stay in `infrastructure/feature_providers/`
  for when it resumes, and `FeatureFetcherSet` keeps its shape. Nothing consumes news or social
  today: `build_feature_history_fn` yields features only for `strategy_style == "alternative"`,
  `_ALTERNATIVE_FEATURE_FETCHER_ATTRS` is empty, and all eight registered strategies are `trend` or
  `mean_reversion`. The daily run no longer wires those two fetchers. The **policy** provider is not
  in this bucket: it is genuinely live, supplying `fetch_regime` to rotation's regime-fit component
  from both the trading run and the shadow-eval job.
- **Feature-provider enablement is not data.** Providers are constructed unconditionally at the
  composition root, so nothing ever read the `feature_providers` table. Its repository, record, and
  fixture seeding were deleted on 2026-08-10; the table itself stays until the migration squash.
  Re-enabling the deferred work above needs no catalog — only the provider implementations, which
  are untouched.

## Known limitations

- **New signal *logic* is a code change.** The `strategies` catalog is canonical for strategy
  definitions and knobs — variants and tuning are data, editable via CLI and resolved at runtime from
  catalog rows. A genuinely new *signal primitive* needs a new signal function + `PRIMITIVE_CATALOG`
  entry: the catalog composes primitives, and there is no scripting layer for new logic.
- **No single-day risk figures.** `daily_metrics.drawdown_pct` and `risk_snapshots.daily_loss_pct`
  are always `NULL`: both need intraday equity this codebase does not persist, and a trailing-history
  figure cannot stand in for one day's. Other columns are populated, several of them conditionally —
  [Performance and Risk Tables](reference/performance-and-risk-tables.md) owns the full contract.

## How it works (architecture)

- **Layering:** `interfaces → services → repositories/domain → database`, with `models/` as the
  lowest passive-data layer. Enforced by `scripts/checks/repo/layer_check.py`. See
  [architecture conventions](architecture/architecture-conventions.md).
- **Interface primacy:** the scheduler (runtime jobs) and CLI are the primary drivers; the web UI is
  an optional consumer over the same `src/trading/` services. What that requires of new work is in
  [architecture conventions](architecture/architecture-conventions.md).
- **Broker seam:** service/domain code depends only on the `BrokerConnection` port; the factory is
  the sole place broker routing and the `live_trading_enabled` guard live. A new environment is one
  adapter + one factory branch. No automated process sets `live_trading_enabled` — automation
  evaluates and proposes, a human decides whether real money can move.
- **Feature-provider isolation:** external API libraries are imported only inside
  `src/infrastructure/feature_providers/`; the interface layer wires them in.
- **Persistence:** SQLite with a linear, numbered Alembic migration system
  ([reference](reference/db-migration-system.md)).
- **Directory maps:** [trading package map](maps/trading-package-map.md),
  [UI map](maps/ui-map.md), [scripts map](maps/scripts-map.md).

## How you operate it

- **Primary:** runtime scheduler jobs and CLI commands, run from the repository root with the virtual
  environment active. Configuration is via account profiles, operational settings, and database
  entries. See the [runtime jobs reference](reference/runtime-jobs.md) and
  [operator runbooks](runbooks/README.md).
- **Optional:** the `apps/paper_trading_web` UI for viewing results and account configuration.
- **Adding an account or a strategy variant:** a data change — accounts via profiles, variants via
  the `strategies` catalog. No deploy.

## Scope boundaries

- **Trends workflow** — `apps/trends/` is a standalone CLI, reachable only from the command line.
- **Alternative data** — policy signals are derived from ETF proxies, not from policy datasets
  directly.
- **IBKR connectivity** — the Client Portal / Web API is the primary integration; a TWS/IB Gateway
  socket integration exists alongside it, over `ib_async` or a native `ibapi` client. See
  [broker integration](reference/broker-integration.md) for what each transport supports and
  [ADR 018](adr/018-broker-transport-venue-matrix.md) for how transport and venue are modelled.
