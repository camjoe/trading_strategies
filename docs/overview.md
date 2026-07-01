# Trading Strategies — App Overview

Type: overview
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-07-01
Purpose: Definitive top-level explainer and guiding north star for the app — what it is, what it can
do today (honestly, including known gaps), how it works, and where it is going. Entry point that
frames the detailed backlog in [plan.md](plan.md) and the plans it references.
Related: [Plan](plan.md), [Sleeves & Accounts Convergence Plan](sleeves-accounts-convergence.md),
[DB Schema Rewrite Spec](db-schema-rewrite-spec.md),
[Architecture Conventions](architecture/architecture-conventions.md), [Docs Index](README.md)

> This document is the definitive guideline. When priorities or capabilities change, update this
> file first, then reconcile the detailed items in [plan.md](plan.md).

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
- **Sleeve** — a strategy-execution unit inside an account (one broker account can host several
  independent strategy sleeves). See [ADR 003](adr/003-sleeve-virtualization-architecture.md).
- **Strategy** — a named signal specification (`StrategySpec`) with a signal function and default
  parameters. 14 are registered today across trend, mean-reversion, oscillator, breakout, and
  external-data ("alternative") families.
- **Parameter set** — a versioned set of tunable parameters for a strategy (`StrategyParamSetRepository`).
- **Evaluation** — the canonical `StrategyEvaluationArtifact`: backtest + walk-forward + paper/live
  evidence fused into confidence and a blended decision score.
- **Rotation** — automated switching of the active strategy (champion/challenger for sleeves;
  episode-based for accounts) based on evaluation.
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
- **Sleeve virtualization** — one broker account hosting multiple strategy sleeves, with
  champion/challenger rotation, a pre-submit risk gate + kill switches, and equity reconciliation.
- **Account-level rotation** (episode-based) as a separate, earlier paradigm.
- **Broker abstraction** — paper adapter, IBKR Web API adapter, legacy socket adapter, behind one
  port + factory, with a hard `live_trading_enabled` safety guard.
- **Feature providers** — news, social, and policy (ETF-proxy) sources for alternative strategies.
- **Runtime scheduler jobs** (daily backtest refresh, challenger shadow evaluation, governance,
  health checks, reporting) plus a **CLI** and an optional **web UI** (`apps/paper_trading_web`).
- **Operational settings** (evaluation confidence, promotion policy, trade throttles) and
  **account profiles** for configuration.

## Known gaps / honest current state

These are real and shape the plan. None are hidden by the UI — they are core-logic gaps.

- **The execution loop is not closed (keystone gap).** The paper/live trade path selects trades with
  a legacy random/style-biased placeholder — an early proof-of-concept built to prove out
  auto-checking trades and the IBKR hookup, *before* the strategy/evaluation features existed. It
  does **not** run the strategy signal functions. Strategy signals currently run **only in
  backtests**. Consequence: rotation switches the strategy label/style bias, but live/paper does not
  actually trade the selected strategy — the evaluate → rotate → trade loop is broken at the last
  mile.
- **Parameter sets are not applied to signal evaluation.** They are stored and governed, but backtests
  use the strategy's code-level `default_params`, and the live path does not use them at all. "Different
  parameters" is therefore not yet a real, end-to-end data lever.
- **Strategies are code, not data.** Adding a genuinely new strategy requires a new signal function
  and a `STRATEGY_REGISTRY` edit. Adding a *variant/tuning* of an existing strategy should be data,
  but only once parameters are wired through (above).
- **Two rotation paradigms and duplicated account/sleeve orchestration** — see the
  [Sleeves & Accounts Convergence Plan](sleeves-accounts-convergence.md).
- **Parameters are scattered** across ~5 stores with no single view — see Plan Next "Unified
  parameter source".

## How it works (architecture)

- **Layering:** `interfaces → services → repositories/domain → database`, with `models/` as the
  lowest passive-data layer. Enforced by `scripts/checks/layer_check.py`. See
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
- **Optional:** the `apps/paper_trading_web` UI for viewing results and editing parameters.
- **Adding data (target workflow):** new accounts and (once parameters are wired) new parameter sets
  for existing strategies should be data changes; new strategy *logic* and new feature providers are
  contained code additions.

## Direction & plan (north star)

The high-level priority order below is the strategic north star. The **authoritative, itemized
tracker** (tasks / order / status / timelines) is [plan.md](plan.md); open decisions ("what needs
defining") are consolidated in [decisions.md](decisions.md); convergence detail lives in the
[convergence plan](sleeves-accounts-convergence.md).

1. **Close the execution loop (keystone).** Wire strategy signals into live/paper execution and apply
   parameter sets to signal evaluation end-to-end, so the trader actually runs the strategy (and
   params) it is evaluated on. Without this, the evaluation/rotation machinery selects strategies the
   live path never executes. *This is the highest priority and should precede polishing the
   evaluate/rotate loop.*
2. **Finish unified evaluation** — the shared decision-score contract now backs compare, promotion,
   and sleeve rotation (Now #1a/#1b done); complete the cross-surface regression tests (1c).
3. **Plug-and-play strategy & provider catalog.** Make the strategy registry data-driven (a code
   catalog of tested signal *primitives* + data-defined strategy definitions), and make feature
   providers pluggable, so new variants/accounts are data changes.
4. **Converge accounts and sleeves** onto shared services (submission, rotation, accounting) — see
   the convergence plan.
5. **Unified parameter source** — one place to view/edit tunable parameters (service-first, UI
   optional).
6. **Decisioning legibility & naming pass** — behavior-preserving structure/naming so the
   evidence → score → promotion/rotation flow is legible.
7. **Later:** adaptive learning, portfolio-level risk rollup, strategy parameter optimization.

## Guiding constraints

- **Live execution stays explicitly human-gated** — no automated process sets `live_trading_enabled`.
- **Interface primacy** — scheduler/CLI first, UI optional; logic lives in `src/trading/`.
- **UI follows the contract, per feature** — never designed on unsettled contracts.
- **Signal primitives are code; strategy definitions/params are data** — no arbitrary-logic scripting
  DSL.
- **Feature providers are signal inputs, not evaluation evidence** — their effect reaches evaluation
  only through realized paper/live P&L.
- **One evidence-driven evaluation** backs comparison, rotation, and promotion.
