# `src/` Restructure — Notes

Type: architecture
Status: Complete (foundation phase)
Created: 2026-06-22
Last Reviewed: 2026-06-24
Purpose: Retain the durable outcome, reusable patterns, and the one open question from the `src/` restructure. The detailed commit plan, per-move runbook, and target-structure inventory that drove the work were removed once complete — they now live in the code, `architecture-conventions.md`, and git history.
Related: [Architecture Conventions](architecture-conventions.md), [Trading Package Map](../maps/trading-package-map.md)

## Outcome

The foundation phase is **done**. The repo has a clean three-sibling base — `src/trading`, `src/infrastructure`, `src/common` — alongside `apps/`, with infrastructure genuinely separated from the trading domain:

- The former root `trading` and `common` packages now live under `src/`; infrastructure subpackages live under `src/infrastructure` (brokers, feature_providers, market_data, database, config).
- Market data: the `MarketDataProvider` port and the proxy feature provider stay in `src/trading/services/market_data`; the concrete yfinance adapter + factory + transport cache live in `src/infrastructure/market_data`, wired at composition seams. No global provider locator.
- Boundaries are enforced by `scripts/checks/repo/layer_check.py` — e.g. `src/trading` code must not import the `infrastructure.market_data` adapter (mirroring brokers/feature_providers).

## Reusable patterns (for any future structural move)

- **DI at composition seams, not globals.** Define the port in the domain/service layer; build the concrete adapter via a factory imported only at interface/composition seams (CLI, runtime jobs, web routes, the backtest entry). Mirror `broker_factory` / `build_provider`.
- **Move the concrete adapter LAST.** Thread the dependency injection first while the adapter (and any global) stay put; relocating the adapter before DI causes a circular import (infra → the package `__init__` → back into the half-initialised infra module).
- **One move per commit, always green.** `git mv` + import codemod + move tests + update tooling (layer check / ruff / mypy / coverage / maps / docs) in the *same* commit; finish with `python -m scripts.run_checks quick` green.
- **Relocating a package under `src/` is a pure `git mv`** — the package name is unchanged and `src/` is a discovery root via the editable install, so there are no import rewrites; re-run `pip install -e .` once. NB: a package entering `src/` also enters mypy's checked set, which can surface latent type issues in its consumers.

## Open question — domain slicing

The remaining decision is whether to carve more `sleeves`-like bounded contexts out of the layer-first structure. Guidance: **slice by coupling, not uniformly**, and treat it as a separate effort — start with an analysis pass (identify the most cohesive/coupled candidates) before any moves. Not started.
