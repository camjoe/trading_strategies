# Project Overview

Type: overview
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-07-26
Purpose: Explain the project's current capabilities, concepts, architecture, limitations, and scope.
Related: [Architecture Conventions](architecture/architecture-conventions.md), [Docs Index](README.md)

## What this app is

A research framework for developing, backtesting, and paper-trading quantitative strategies. It
supports historical backtesting and walk-forward optimization, simulated execution, strategy
comparison, and human-reviewed promotion workflows. Broker-connected and live-trading paths are advanced,
experimental surfaces protected by explicit safety gates.

Design goals:

- **Try strategies and parameters quickly** — ideally adding strategy variants and accounts as
  *data*, not code.
- **One evidence-driven evaluation** feeding comparison, rotation, and promotion decisions.
- **Human-gated broker execution** — automation can evaluate and propose; a human controls whether
  live trading is enabled.
- **Scheduler and CLI first** — the web UI is an optional view and configuration convenience.

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
  evidence.
- **Broker / environment** — paper simulator, IBKR Web API, or IBKR socket API, all behind one
  `BrokerConnection` port and factory. Paper vs. IBKR-paper vs. live differ by adapter + the
  `live_trading_enabled` guard, not by separate code paths.

## What it can do today

- **Multi-strategy backtesting and walk-forward optimization** (`backtest-optimize`) that run the
  real strategy signal functions, persist completed result trees atomically, distinguish run
  purpose, and derive experiment/window summaries from member runs. The older rolling-window
  robustness path was retired — see [ADR 016](adr/016-optimizer-experiments-as-research-evidence.md).
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
- **Feature providers** — news, social, and policy (ETF-proxy) sources for alternative strategies.
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

## Known limitations

These limitations describe current behavior and maturity; they are not hidden by the UI.

- **New signal *logic* is still a code change.** The `strategies` catalog is canonical for
  strategy definitions and knobs — variants and tuning are data, editable via CLI and resolved at
  runtime from catalog rows. But a genuinely new *signal primitive* still needs a new signal function
  + `PRIMITIVE_CATALOG` entry: the catalog composes primitives, it does not script new logic.
- **Daily performance metrics are partially populated.** The daily-metrics writer runs from the
  snapshot step and derives `return_pct`, `turnover_pct`, `slippage_bps`, `trade_count`, `fees_total`,
  `hit_rate`/`expectancy` (from each closing order's realized P&L), and `risk_adjusted_score` (a
  trailing annualized Sharpe over the book's recent daily returns, `NULL` until enough history
  accrues). One column stays `NULL`: `drawdown_pct` (single-day peak-to-trough needs intraday equity
  this codebase does not persist). See [Performance and Risk Tables](reference/performance-and-risk-tables.md)
  for the table contract.

## How it works (architecture)

- **Layering:** `interfaces → services → repositories/domain → database`, with `models/` as the
  lowest passive-data layer. Enforced by `scripts/checks/repo/layer_check.py`. See
  [architecture conventions](architecture/architecture-conventions.md).
- **Interface primacy:** the scheduler (runtime jobs) and CLI are the primary drivers; the web UI is
  an optional consumer over the same `src/trading/` services. Every capability must be reachable from
  the scheduler/CLI without the UI; contracts are never shaped around the UI.
- **Broker seam:** service/domain code depends only on the `BrokerConnection` port; the factory is
  the sole place broker routing and the `live_trading_enabled` guard live. A new environment is one
  adapter + one factory branch.
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
- **Adding data:** new accounts and new strategy variants are data changes today (variants via the
  `strategies` catalog); new signal *logic* and new feature providers remain contained code
  additions.

## Design boundaries

- **Live execution stays explicitly human-gated** — no automated process sets `live_trading_enabled`.
- **Interface primacy** — scheduler/CLI first, UI optional; logic lives in `src/trading/`.
- **UI follows the contract, per feature** — never designed on unsettled contracts.
- **Signal primitives are code; strategy definitions/params are data** — no arbitrary-logic scripting
  DSL.
- **Feature providers are signal inputs, not evaluation evidence** — their effect reaches evaluation
  only through realized paper/live P&L.
- **One evidence-driven evaluation** backs comparison, rotation, and promotion.

## Current scope boundaries

- **Trends workflow** — `apps/trends/` is a standalone CLI and is not integrated into the API or UI.
- **Alternative data** — current policy signals use ETF-proxy feature providers rather than direct
  non-proxy policy datasets.
- **IBKR connectivity** — the Client Portal / Web API is the primary integration. The TWS/IB
  Gateway socket integration supports `ib_async`; its native `ibapi` client has connection,
  order submission/cancellation, open-order refresh, status, execution, commission, rejection,
  positions, account summaries, snapshot quotes, and shutdown handling.
