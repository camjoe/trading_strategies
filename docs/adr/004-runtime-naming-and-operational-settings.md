# ADR: Disambiguate "runtime" Naming and Consolidate Operational Settings

Type: adr
Status: Accepted
Created: 2026-06-25
Last Reviewed: 2026-06-25
Purpose: Record the decision to remove the overloaded "runtime" term from service package names and merge runtime_settings/runtime_throttle into a single operational_settings package.
Related: [Architecture Conventions](../architecture/architecture-conventions.md), [Trading Package Map](../maps/trading-package-map.md), [Navigation Guide](../architecture/nav-guide.md)

## Context

The word "runtime" was overloaded across `src/trading/`, carrying two unrelated meanings:

1. The scheduler/job transport layer at `src/trading/interfaces/runtime/` ("the runtime execution context").
2. A "applies during runtime operation" qualifier on service packages: the former `runtime_settings` and `runtime_throttle` packages under `src/trading/services/` (since merged — see Decision).

This collided at the import-path level — `trading.services.runtime_settings` versus `trading.interfaces.runtime` — making it ambiguous whether a `runtime_*` name referred to the scheduler layer or to operational configuration. The two settings packages were also already tightly coupled: `RuntimeThrottleSettings` lived in `runtime_settings/models.py` and `runtime_throttle/enforcement.py` imported it back from `runtime_settings`.

Alternatives considered for the merged package name: `runtime_config` (still carries "runtime"), `policy_settings` (overlaps with the existing `promotion_policy` concept), and bare `settings` (risks confusion with the `global_settings` table/repository that backs it). `operational_settings` was chosen because it fully drops the "runtime" word and accurately describes operator-tunable settings applied during operation.

Renaming the in-package `runtime_*` qualifiers (`services/auto_trading/runtime*.py`, `services/accounts/runtime_loader.py`) was considered and rejected: there "runtime" accurately distinguishes runtime-*execution* code from decision/input code, the names are scoped inside a package so they do not collide at the top level, and renaming would be high-churn for little clarity gain.

## Decision

1. "runtime" in a module/package path means the scheduler transport layer, and `src/trading/interfaces/runtime/` is the only place that meaning applies.

2. Operator-tunable settings applied during runtime operation (evaluation confidence, promotion policy, trade throttles) live in `src/trading/services/operational_settings/` — the merger of the former `runtime_settings/` and `runtime_throttle/` packages. New settings of this kind go here.

3. In-package `runtime_*` qualifiers that mean "runtime-execution code vs. decision/input code" are intentional and stay.

4. Public symbol names that still contain "runtime" (`enforce_runtime_trade_throttles`, `RuntimeThrottleSettings`, the `runtime_max_trades_per_*` setting keys) were left unchanged to keep the rename's blast radius tight. Changing them is a separate, optional follow-up — they touch DB-persisted setting keys and error-message text.

## Consequences

Benefits:

- Import paths are unambiguous; no package name competes with `interfaces/runtime/`.
- The two coupled settings packages become one cohesive surface.

Trade-offs / follow-ups:

- Module/package paths and the public symbol names temporarily disagree (paths say `operational_settings`, some symbols still say `runtime`). A future ADR/change may align the symbol names if the churn is judged worthwhile.
- Do not reintroduce `runtime_settings`/`runtime_throttle` packages.
