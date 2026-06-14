# Project Structure

Root overview of the trading strategies monorepo. For deeper navigation, see the per-app maps and the task-oriented nav guide linked below.

## Top-Level Directories

| Directory | Description |
|---|---|
| `trading/` | Core trading engine — layered Python package (interfaces → services → repositories → domain → database → models) |
| `paper_trading_ui/` | Operator UI — FastAPI backend + TypeScript/Vite frontend |
| `brokers/` | Broker adapters (paper + live); injected at the interface layer; `trading/` must never import from here except via `trading/interfaces/` |
| `features/` | External-data feature providers for alternative strategies; bounded context |
| `tests/` | Test suite; mirrors the source tree path-for-path |
| `scripts/` | Dev and ops tooling — checks, data ops, documentation sync, UI launcher |
| `docs/` | Architecture docs, runbooks, reference notes, ADRs |
| `common/` | Shared utilities available to all packages (used sparingly) |
| `trends/` | Trend/signal data assets |
| `.github/` | Bot instructions, architecture conventions, style guide, and skill definitions |

## Per-App Maps

- [`docs/architecture/trading-package-map.md`](architecture/trading-package-map.md) — Layering rules and full module directory for `trading/`
- [`docs/architecture/ui-map.md`](architecture/ui-map.md) — Structure of `paper_trading_ui/backend/` and `paper_trading_ui/frontend/`
- [`docs/architecture/scripts-map.md`](architecture/scripts-map.md) — All `scripts/` modules and what they do

## Task Navigation

- [`docs/architecture/nav-guide.md`](architecture/nav-guide.md) — "I want to X → look/edit Y" lookup table

## Other Architecture Docs

- [`docs/architecture/service-cookbook.md`](architecture/service-cookbook.md) — Which function to call for common tasks
- [`docs/architecture/service-repository-boundary.md`](architecture/service-repository-boundary.md) — Service/repository contract rules
- [`.github/BOT_ARCHITECTURE_CONVENTIONS.md`](../.github/BOT_ARCHITECTURE_CONVENTIONS.md) — Authoritative layering and import boundary rules