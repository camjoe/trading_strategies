# Trading Service API — Developer Cookbook

Type: architecture
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-07-13
Purpose: Answer "which package do I call for X?" — the supported internal import pattern plus
capability → service-package pointers. The per-function surface lives in each package's `__init__.py`
(`__all__`), not here.
Related: [Service/Repository Boundary](service-repository-boundary.md), [Navigation Guide](nav-guide.md), [Trading Package Map](../maps/trading-package-map.md)

## Purpose

Answer the question: **"Which service package do I reach for to do X?"**

This is a task-oriented companion to [trading-package-map.md](../maps/trading-package-map.md).
Use it when writing CLI commands, runtime jobs, or UI backend routes that need `src/trading/services/`.

This doc deliberately does **not** mirror function signatures — an earlier version hand-maintained
~70 of them and they drifted. Most packages' `__init__.py` files re-export their supported internal
surface via `__all__`; **read that (or the module docstrings) for the current functions and
signatures.**

These exports define the preferred integration boundary within this repository. They are not a
versioned compatibility promise for external consumers.

---

## Import pattern

Most service packages expose a supported internal `__all__` surface through their
`__init__.py`. Import from the package by default, not from the concrete submodule:

```python
# Correct — supported internal surface
from trading.services.accounts import get_account, list_account_records
from trading.services.reporting import build_account_stats, build_live_benchmark_overlay

# Avoid — internal submodule (subject to change without notice)
from trading.services.accounts.queries import get_account
```

Naming conventions on that surface (see `architecture-conventions.md`): reads are `fetch_*`/`get_*`/
`list_*`/`find_*`, side-effect workflows are `run_*`/`execute_*`/`record_*`/`set_*`, input/config
derivation is `resolve_*`.

Exception: `trading.services.execution` is intentionally submodule-oriented for now. Import the
focused module that owns the safety-critical concern (`submission`, `gate`, `pre_submit_gate`, `nav`,
or `reconciliation`) instead of treating the package root as a facade.

---

## Capability → package

| I need to… | Package | Scope notes |
|---|---|---|
| Look up, list, create, or configure accounts; change strategy/benchmark | `trading.services.accounts` | Strict (`get_*`) vs optional (`find_*`) lookups; runtime-eligible listing |
| Apply named preset profiles to an account | `trading.services.profiles` | Profile loading + application (`profile_source` is the input-backend abstraction) |
| Load account state; record trades; list trades | `trading.services.accounting` | Cash/positions/cost state + the trade ledger write path |
| Account stats, equity/settlement math, benchmark overlays, CLI reports, snapshots | `trading.services.reporting` | Also owns compare-strategies and snapshot history display |
| Fetch prices | `trading.services.pricing` | Latest-price lookups over the injected provider |
| Get/switch the market-data or feature provider | `trading.services.market_data` | Ports + `require_*` guards; concrete adapter lives in `src/infrastructure/market_data/` |
| Run auto-trading for accounts; rotation-if-due; broker-order reconciliation | `trading.services.auto_trading` | Runtime orchestration; injected `broker_factory` and provider |
| Submit book intents, reconcile fills/NAV, or run pre-submit gates | `trading.services.execution.<focused_module>` | Shared clean-schema order-submission path for every book; submodule-oriented surface |
| Book execution, fills, risk gate, rotation, reconciliation | `trading.services.books` | Shares trade selection with `auto_trading` |
| Book performance windows; portfolio risk snapshots; account analysis | `trading.services.analysis` | Flat service modules (`performance.py`, `risk_snapshots.py`) — import directly |
| Seed, resolve, create, configure, or freeze strategy catalog rows | `trading.services.strategy_catalog` | Strategy primitive + `params_json` resolution and catalog edits |
| Read or edit the unified parameter source | `trading.services.parameters` | View/edit surface over global settings, book settings, and strategy rows |
| Promotion assessments, review requests/actions, history | `trading.services.promotion` | Human-gated review workflow + CLI rendering |
| Canonical strategy evaluation (evidence + decision score) | `trading.services.evaluation` | Backs compare, rotation, and promotion via `derive_decision_score` |
| Operational settings: throttles, evaluation confidence, promotion policy | `trading.services.operational_settings` | Also owns trade-throttle enforcement |
| Find stale backtest coverage targets | `trading.services.backtesting` | Service-level staleness enumeration/remediation support; the backtest engine remains under `src/trading/backtesting/` |
| Query Autonomy monitor status, artifacts, governance, and risk | `trading.services.autonomy_monitor` | Operator/dashboard read model over DB state and runtime artifacts |
| Bulk admin deletions | `trading.services.admin` | Backup-before-delete pattern applies |
| Resolve trade universes | `trading.services.universe` | Universe name → ticker list |

---

## UI Backend boundary rule

`apps/paper_trading_web/backend/services/` is a **transport-only** layer — HTTP
conversion, FastAPI error handling, and camelCase response shaping only. If a
calculation would be useful to a CLI command or a runtime job, it belongs in
`src/trading/services/`, not the UI backend.

Full rule (allowed/disallowed responsibilities, interface primacy, HTTP error
mapping): [architecture-conventions.md](architecture-conventions.md#ui-backend-boundary-rule).

---

## Related references

- [trading-package-map.md](../maps/trading-package-map.md) — structural overview and placement rules
- [service-repository-boundary.md](service-repository-boundary.md) — how to split service vs repository responsibilities
- `docs/architecture/architecture-conventions.md` — canonical architecture rules for all agents
