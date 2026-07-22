# Trading Strategies

[![Quality Gates](https://github.com/camjoe/trading_strategies/actions/workflows/quality-gates.yml/badge.svg?branch=main)](https://github.com/camjoe/trading_strategies/actions/workflows/quality-gates.yml)
[![Python Tests](https://github.com/camjoe/trading_strategies/actions/workflows/python-tests.yml/badge.svg?branch=main)](https://github.com/camjoe/trading_strategies/actions/workflows/python-tests.yml)
[![Frontend Tests](https://github.com/camjoe/trading_strategies/actions/workflows/frontend-tests.yml/badge.svg?branch=main)](https://github.com/camjoe/trading_strategies/actions/workflows/frontend-tests.yml)
[![Security Checks](https://github.com/camjoe/trading_strategies/actions/workflows/security-checks.yml/badge.svg?branch=main)](https://github.com/camjoe/trading_strategies/actions/workflows/security-checks.yml)

A research framework for developing, backtesting, and paper-trading quantitative strategies.

> [!WARNING]
> This repository is educational and research software. It is not financial, investment, tax, or
> legal advice, and it is not represented as production-ready investment infrastructure. Trading
> involves risk of substantial loss. Backtests, simulations, and paper-trading results do not predict
> future performance. You are responsible for reviewing the software, protecting broker credentials,
> and deciding whether any use—including connection to a broker—is appropriate.

## Project Overview

The project supports a research workflow from historical testing through simulated execution:

- Historical backtests and rolling-window robustness analysis.
- Paper trading with simulated portfolios, performance tracking, and benchmark comparison.
- Multiple strategy families and data-defined parameter variants.
- Strategy evaluation, comparison, promotion review, and champion/challenger rotation.
- Command-line and scheduled runtime workflows, with an optional local web dashboard.
- Experimental broker adapters protected by an explicit human-controlled live-trading gate.

The core focus is research and paper trading. Broker-connected and live-trading paths are advanced,
experimental surfaces and are not required for ordinary development or backtesting.

See the [project overview](docs/overview.md) for the current concepts, capabilities, limitations, and
architecture.

## Directory Structure

| Folder | Purpose |
|---|---|
| `src/trading/` | Strategy, backtesting, paper-trading, evaluation, and runtime logic. |
| `src/infrastructure/` | Database, broker, market-data, and feature-provider adapters. |
| `src/common/` | Shared utilities used across packages. |
| `apps/paper_trading_web/` | Optional local FastAPI and TypeScript dashboard. |
| `apps/trends/` | Standalone trend and technical-indicator analysis. |
| `scripts/` | Development, validation, data-operation, and launch commands. |
| `docs/` | Architecture, reference, operating, and contributor documentation. |
| `tests/` | Python test suite mirroring the source tree. |

## Python Setup

Python 3.14 is currently supported. Create a repository-local virtual environment and install the
development dependency set; it includes the runtime dependencies and an editable install of the
workspace.

Windows PowerShell:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

macOS or Linux:

```sh
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

All Python commands below assume this virtual environment is active. Activate it again after opening
a new terminal.

Node.js 24 is required only for frontend development under
`apps/paper_trading_web/frontend/`.

## Quick Start

Create or upgrade the local paper-trading database to the current schema:

```sh
python -m scripts.data_ops.manage_db_migrations upgrade
```

Application commands verify the schema but never apply migrations automatically. Re-run this
upgrade command after pulling changes that add a database revision.

From there:

- [Backtesting](docs/reference/backtesting.md) documents historical and walk-forward workflows.
- [Paper trading](src/trading/README.md) documents accounts, commands, and runtime jobs.
- [Trends analysis](apps/trends/README.md) documents the standalone indicator workflow.
- [Local dashboard](apps/paper_trading_web/README.md) documents the optional UI.

The repository does not yet provide a single-command seeded demo; adding one is part of the
open-source preparation work.

## Stability

This is a pre-1.0 research project. It does not currently promise compatibility for an external
Python API, CLI contract, configuration format, database schema, or HTTP API. Package-level exports
and documented commands identify the intended internal integration paths, but they may change as the
project evolves.

## Testing

Run the same complete validation profile used by GitHub Actions:

```sh
python -m scripts.run_checks ci
```

The public workflows run Python tests, frontend tests, repository quality gates, documentation
checks, and dependency/security checks. See [GitHub Actions](https://github.com/camjoe/trading_strategies/actions)
for current results.

## Availability and Licensing

This source repository is publicly viewable on GitHub and is being prepared for a future open-source
release, but it is not currently offered under an open-source license. Until a `LICENSE` file is
added, no permission to use, modify, or redistribute the source is granted beyond rights provided by
applicable law and GitHub's Terms of Service.

Apache License 2.0 is the planned license. This statement records intent only and does not grant that
license. See [Open-Source Readiness](docs/reference/open-source-readiness.md) for the remaining steps.

## Documentation Index

- [Project overview](docs/overview.md)
- [Documentation index](docs/README.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
