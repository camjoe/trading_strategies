# Trading Strategies - App Overview

Type: overview
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-07-09
Purpose: Definitive top-level explainer and guiding north star for the app — what it is, what it can
do today (honestly, including known gaps), how it works, and where it is going. The entry point and
the itemized tracker for what remains.
Related: [Architecture Conventions](architecture/architecture-conventions.md), [Docs Index](README.md),
[Pending One-Time DB Steps](pending-deploy-steps.md)

> This document is the definitive guideline for **why/what** and the tracker for what's left. When
> priorities or capabilities change, update this file first.

## What this app is

A system for developing, evaluating, and progressively automating quantitative trading strategies.
It takes a strategy from **backtest → walk-forward → paper → human-gated live**, continuously
compares strategies against one another, and rotates toward the best performer — with the goal of a
**data-driven automated trader that switches strategy based on what it evaluates to be most
effective**, deployable from paper to a live IBKR account in a near-identical way.

Design intent:

- **Try strategies and parameters quickly** — ideally adding strategy variants and accounts as
  *data*, not code.
- **One evidence-driven evaluation** feeding comparison, rotation, and promotion decisions.
- **Human-gated live execution** — automation proposes; a human enables real money.
- **Scheduler and CLI are the product**; the web UI is an optional view/config convenience.

## Core concepts (glossary)

- **Account** — the broker/custody entity. Owns the broker connection, the `live_trading_enabled`
  safety gate, and cash/positions truth. A "test" account is just an account with `broker_type="paper"`.
- **Book** — the execution primitive (D14): a bounded pool of capital inside an account run to one
  strategy; one broker account can host several independent books. (The earlier "sleeve"
  virtualization concept was retired 2026-07-09;
  [ADR 003](adr/003-sleeve-virtualization-architecture.md) is superseded.)
- **Strategy** — a named signal specification (`StrategySpec`) with a signal function and default
  parameters. 14 are registered today across trend, mean-reversion, oscillator, breakout, and
  external-data ("alternative") families.
- **Strategy knobs** — tunable parameters for a strategy primitive. Resolved at runtime from the
  `strategies` catalog row (P6): the primitive's code defaults with the row's `params_json` layered
  on top.
- **Evaluation** — the canonical `StrategyEvaluationArtifact`: backtest + walk-forward + paper/live
  evidence fused into confidence and a blended decision score.
- **Rotation** — automated switching of the active strategy, book-keyed, via champion/challenger on
  the decision-score contract (the account-episode paradigm was retired in P4).
- **Promotion** — the human-gated lifecycle (research → paper → live-review) with audit history.
- **Feature provider** — an external-data source (news, social, policy/ETF-proxy) that influences
  *trade signals* for "alternative" strategies. Feature providers are signal inputs, not evaluation
  evidence.
- **Broker / environment** — paper simulator, IBKR Web API, or legacy socket, all behind one
  `BrokerConnection` port and factory. Paper vs. IBKR-paper vs. live differ by adapter + the
  `live_trading_enabled` guard, not by separate code paths.

## What it can do today

- **Multi-strategy backtesting and walk-forward analysis** that run the real strategy signal
  functions and persist reports.
- **Canonical evaluation** (`src/trading/services/evaluation/`) fusing backtest, walk-forward, and
  paper/live evidence into confidence + a blended score, exposed through one decision-score contract
  (`EvaluationDecisionScore`).
- **Promotion workflow** with research/paper/live-review stages, human gate, and append-only audit.
- **Paper trading** with equity snapshots, trades, and benchmark overlays.
- **Multi-book accounts** — one broker account hosting multiple strategy books, with
  champion/challenger rotation, a pre-submit risk gate + kill switches, and equity reconciliation.
- **Unified rotation/submission/accounting** — accounts and sleeves converged onto one book-keyed
  path (P4); rotation is one champion/challenger model on the decision-score contract.
- **Broker abstraction** — paper adapter, IBKR Web API adapter, legacy socket adapter, behind one
  port + factory, with a hard `live_trading_enabled` safety guard.
- **Feature providers** — news, social, and policy (ETF-proxy) sources for alternative strategies.
- **Runtime scheduler jobs** (daily backtest refresh, challenger shadow evaluation, governance,
  health checks, reporting) plus a **CLI** and an optional **web UI** (`apps/paper_trading_web`).
- **Operational settings** (evaluation confidence, promotion policy, trade throttles) and
  **account profiles** for configuration, plus a **unified parameter source** (P7): one `parameters`
  view over every store with `configure-*` CLI edits for global settings and per-book rotation
  policy.
- **Data-defined strategy variants** (P6): the `strategies` catalog is the canonical runtime source
  for strategy definitions and knobs; operators add and tune variants via `create-strategy-variant`,
  `configure-strategy`, and `freeze-strategy` without a deploy.
- **Cross-account portfolio risk rollup** (P9): exposure, symbol concentration/overlap, and sector
  rollup via CLI, API, and a read-only Portfolio UI tab.

## Known gaps / honest current state

These are real and shape the plan. None are hidden by the UI — they are core-logic gaps.

- **The execution loop is closed (P1, 2026-07-03).** Live/paper selection now evaluates the active
  strategy's signal function per candidate ticker through the same `evaluate_signal(...)` entry the
  backtester uses: trade only on real signals, no forced minimum, a per-run max cap. Rotation now
  changes what the trader actually does. (The legacy random/style-biased placeholder is removed.)
- **New signal *logic* is still a code change.** Since P6 the `strategies` catalog is canonical for
  strategy definitions and knobs — variants and tuning are data, editable via CLI and resolved at
  runtime from catalog rows. But a genuinely new *signal primitive* still needs a new signal function
  + `PRIMITIVE_CATALOG` entry: the catalog composes primitives, it does not script new logic.
- **Settings edits have no change-audit.** P7's edit surface records only `updated_at` per settings
  row; a change-audit log stays deferred until edit volume justifies it.

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
- **Persistence:** SQLite with a hand-rolled migration system
  ([reference](reference/db-migration-system.md)).
- **Directory maps:** [trading package map](maps/trading-package-map.md),
  [UI map](maps/ui-map.md), [scripts map](maps/scripts-map.md).

## How you operate it

- **Primary:** runtime scheduler jobs and CLI commands, run from the repo root with the venv
  interpreter (see [runbooks](runbooks/README.md) and `AGENTS.md`). Configuration is via account
  profiles, operational settings, and DB entries.
- **Optional:** the `apps/paper_trading_web` UI for viewing results and account configuration.
- **Adding data:** new accounts and new strategy variants are data changes today (variants via the
  `strategies` catalog, P6); new signal *logic* and new feature providers remain contained code
  additions.

## Direction and plan

The strategic order here is the north star (the "why/what") and the authoritative, itemized tracker
for what is left. Durable decisions live in [ADRs](adr/); completed implementation narrative
lives in git history.

The spine (P1–P5) is complete: the execution loop is closed so strategy signals drive live/paper
execution (P1); evaluation is unified behind one decision-score contract that backs compare,
promotion, and rotation (P2); the clean book schema is live (P3); accounts and sleeves are converged
onto one book-keyed submission/rotation/accounting path (P4, with the sleeve vocabulary fully
retired 2026-07-09); and the decisioning naming pass landed alongside (P5). Email notifications
(P8), the unified parameter source (P7), and the portfolio risk rollup (P9) are in. The
execution-mode collapse landed with book-owned rotation scheduling (ADR 014): one book-keyed
runtime path, rotation gated per book and evaluated continuously under cooldown. Backtest freshness
(P12) ships as a non-blocking advisory staleness diagnostic on evaluations (CLI + web); the daily
backtest-refresh job and the `refresh-stale-backtests` command close the loop by re-running only the
stale or missing backtests across each account's rotation candidates. The plug-and-play strategy
catalog (P6) made the `strategies` catalog canonical for definitions and knobs, with CLI edits for
variants and the legacy parameter-set store retired.

The only **committed** work remaining is two one-time DB deploy steps (sleeve-retirement migration
and the book-rotation cutover — operator runbooks) plus one not-yet-built schema cleanup, all tracked
in [pending-deploy-steps.md](pending-deploy-steps.md).

## Guiding constraints

- **Live execution stays explicitly human-gated** — no automated process sets `live_trading_enabled`.
- **Interface primacy** — scheduler/CLI first, UI optional; logic lives in `src/trading/`.
- **UI follows the contract, per feature** — never designed on unsettled contracts.
- **Signal primitives are code; strategy definitions/params are data** — no arbitrary-logic scripting
  DSL.
- **Feature providers are signal inputs, not evaluation evidence** — their effect reaches evaluation
  only through realized paper/live P&L.
- **One evidence-driven evaluation** backs comparison, rotation, and promotion.

## Out of scope (do not silently re-add)

- **Trends workflow integration into API/UI** — `apps/trends/` stays a standalone CLI.
- **Non-proxy alternative-data expansion** — ETF-proxy feature providers are sufficient for now.
- **Native `IbApiClient` socket path** — the Client Portal / Web API client is the active IBKR
  integration; the legacy socket path stays documented stubs only.
