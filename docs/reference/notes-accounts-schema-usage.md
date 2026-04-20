# Architecture Notes: Accounts Schema Usage

Status: Active audit  
Date: 2026-04-14  
Audience: Developers, Deep Code Review bot, DB Migration Steward bot

---

## Overview

This document tracks how the `accounts` table is actually used across the
repository. The goal is to support evidence-based cleanup: before removing,
consolidating, or hiding any account field, we first record where it is written,
where it is read, and whether it participates in real runtime logic.

This is a **living audit**, not a promise that every field below should remain
forever. Fields marked **unclear / revisit** or **active but niche** are the
most likely follow-up targets for later simplification passes.

---

## Classification Legend

- **core active** — broad write + read usage and/or important runtime behavior
- **active but niche** — real production usage, but scoped to a narrower feature
- **config / display oriented** — used mainly for account setup and operator-facing output
- **manual / safety-critical** — intentionally narrow, but important guardrail state
- **unclear / revisit** — present in schema and surfaced in code, but still a good future cleanup candidate

---

## Core Identity and Benchmark Fields

| Column | Write paths | Read / logic paths | Classification | Notes |
| --- | --- | --- | --- | --- |
| `name` | `accounts/mutations.py`, admin create route | repository lookup, CLI/UI routing, reporting, promotion, runtime account selection | **core active** | Primary account identity; effectively immutable after create |
| `strategy` | `accounts/mutations.py`, `profiles_service.py`, UI params route | runtime strategy resolution, backtesting, reporting, promotion, rotation fallback | **core active** | Central behavioral field |
| `initial_cash` | `accounts/mutations.py`, admin create route, profiles | reporting, backtesting, runtime/account-state math, rotation overlay ticker derivation | **core active** | Core accounting input |
| `created_at` | `accounts/mutations.py` | reporting, benchmark comparison timing, UI summaries | **core active** | Historical metadata with live reporting value |
| `benchmark_ticker` | `accounts/mutations.py`, `set_benchmark()`, profiles, admin create route | reporting, backtesting, UI summaries and live benchmark overlay | **core active** | Shared across account, backtest, and UI comparison flows |
| `descriptive_name` | `accounts/mutations.py`, profiles, admin create route, UI params route | account listing, reporting, UI summaries | **config / display oriented** | Strongly used, but mostly presentational |

---

## Goal, Risk, and General Trading Policy Fields

| Column | Write paths | Read / logic paths | Classification | Notes |
| --- | --- | --- | --- | --- |
| `goal_min_return_pct` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | listing, reporting, UI summary payloads | **config / display oriented** | Used for operator goals, not core execution logic |
| `goal_max_return_pct` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | listing, reporting, UI summary payloads | **config / display oriented** | Same role as min goal |
| `goal_period` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | listing, reporting, UI summary payloads | **config / display oriented** | Shapes goal metadata presentation |
| `learning_enabled` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | account listing, runtime trade selection, UI summaries | **core active** | Affects runtime behavior, not just display |
| `risk_policy` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | account listing, trade execution risk-based sell logic, UI/reporting | **core active** | Used directly by runtime sell policy |
| `stop_loss_pct` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | trade execution risk logic, UI summaries, reporting | **core active** | Part of active runtime risk policy |
| `take_profit_pct` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | trade execution risk logic, UI summaries, reporting | **core active** | Part of active runtime risk policy |
| `trade_size_pct` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | runtime buy sizing, backtest sizing, listing, UI/reporting | **core active** | One of the clearest active config fields |
| `max_position_pct` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | runtime buy sizing, backtest sizing, listing, UI/reporting | **core active** | Paired with `trade_size_pct` in active execution logic |
| `instrument_mode` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | listing, runtime execution path, UI/reporting | **core active** | Drives equity vs LEAPs execution mode |

---

## LEAPs / Options Tuning Fields

| Column | Write paths | Read / logic paths | Classification | Notes |
| --- | --- | --- | --- | --- |
| `option_strike_offset_pct` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | `domain/auto_trader_policy.py`, reporting, UI summaries | **active but niche** | Real runtime use, but only in LEAPs-capable flows |
| `option_min_dte` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | trade execution option premium estimation, reporting, UI summaries | **active but niche** | Real runtime use for LEAPs |
| `option_max_dte` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | trade execution option premium estimation, reporting, UI summaries | **active but niche** | Real runtime use for LEAPs |
| `option_type` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | validation, UI summaries, reporting | **active but niche** | Presently more filter/config than heavy runtime driver |
| `target_delta_min` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | `domain/auto_trader_policy.py` candidate filtering, reporting | **active but niche** | Used in options candidate gating |
| `target_delta_max` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | `domain/auto_trader_policy.py` candidate filtering, reporting | **active but niche** | Used in options candidate gating |
| `max_premium_per_trade` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | `domain/auto_trader_policy.py` LEAPs sizing limits, reporting | **active but niche** | Runtime-relevant in LEAPs flows |
| `max_contracts_per_trade` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | `domain/auto_trader_policy.py` LEAPs sizing limits, reporting | **active but niche** | Runtime-relevant in LEAPs flows |
| `iv_rank_min` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | `domain/auto_trader_policy.py` options candidate filtering, reporting | **active but niche** | Real filter logic, narrower use |
| `iv_rank_max` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | `domain/auto_trader_policy.py` options candidate filtering, reporting | **active but niche** | Real filter logic, narrower use |
| `roll_dte_threshold` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | reporting/UI summaries; limited visible runtime use in current pass | **unclear / revisit** | Survives config and display flows, but deserves a later targeted runtime-use check |
| `profit_take_pct` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | reporting/UI summaries; limited visible runtime use in current pass | **unclear / revisit** | Present and surfaced, but not yet strongly evidenced in runtime behavior |
| `max_loss_pct` | CLI/shared config, `accounts/mutations.py`, profiles, admin/UI update paths | reporting/UI summaries; limited visible runtime use in current pass | **unclear / revisit** | Same as `profit_take_pct` |

---

## Rotation and Overlay Fields

| Column | Write paths | Read / logic paths | Classification | Notes |
| --- | --- | --- | --- | --- |
| `rotation_enabled` | `profiles_service.py`, `RotationConfig`, UI params route, admin create route, runtime state updates | listing, evaluation/promotion context, rotation runtime entry gating, UI summaries | **core active** | Central rotation feature gate |
| `rotation_mode` | `profiles_service.py`, `RotationConfig`, UI params route, admin create route | runtime rotation selection, UI summaries | **core active** | Determines major rotation behavior |
| `rotation_optimality_mode` | `profiles_service.py`, `RotationConfig`, UI params route, admin create route | rotation strategy selection, UI summaries | **core active** | Used in runtime selection scoring |
| `rotation_interval_days` | `profiles_service.py`, `RotationConfig`, UI params route, admin create route | due checks and validation, UI summaries | **core active** | One of the schedule-driving fields |
| `rotation_interval_minutes` | `profiles_service.py`, `RotationConfig`, UI params route, admin create route | due checks and validation, UI summaries | **core active** | Minute-granularity schedule control |
| `rotation_lookback_days` | `profiles_service.py`, `RotationConfig`, UI params route, admin create route | runtime optimal-strategy selection, UI summaries | **core active** | Shapes historical evaluation window |
| `rotation_schedule` | `profiles_service.py`, `RotationConfig`, UI params route, admin create route | runtime strategy selection, validation, UI summaries | **core active** | Key rotation configuration surface |
| `rotation_regime_strategy_risk_on` | `profiles_service.py`, `RotationConfig`, UI params route, admin create route | regime-based selection, validation, UI summaries | **active but niche** | Only meaningful for regime rotation |
| `rotation_regime_strategy_neutral` | `profiles_service.py`, `RotationConfig`, UI params route, admin create route | regime-based selection, validation, UI summaries | **active but niche** | Only meaningful for regime rotation |
| `rotation_regime_strategy_risk_off` | `profiles_service.py`, `RotationConfig`, UI params route, admin create route | regime-based selection, validation, UI summaries | **active but niche** | Only meaningful for regime rotation |
| `rotation_overlay_mode` | `profiles_service.py`, `RotationConfig`, UI params route, admin create route | overlay vote selection and validation, UI summaries | **active but niche** | Real runtime behavior, but narrower than base rotation |
| `rotation_overlay_min_tickers` | `profiles_service.py`, `RotationConfig`, UI params route, admin create route | overlay confidence logic, UI summaries | **active but niche** | Runtime threshold tuning |
| `rotation_overlay_confidence_threshold` | `profiles_service.py`, `RotationConfig`, UI params route, admin create route | overlay confidence logic, UI summaries | **active but niche** | Runtime threshold tuning |
| `rotation_overlay_watchlist` | migration backfill, `profiles_service.py`, `RotationConfig`, UI params route | overlay ticker resolution, UI summaries | **core active** | Used directly to derive overlay ticker universe |
| `rotation_active_index` | `profiles_service.py`, `RotationConfig`, UI params route, runtime rotation state updates | runtime active strategy resolution, UI summaries | **core active** | Mutable runtime state, not just setup config |
| `rotation_last_at` | `profiles_service.py`, `RotationConfig`, UI params route, runtime rotation state updates | due checks, episode sync, UI summaries | **core active** | Important runtime timing state |
| `rotation_active_strategy` | `profiles_service.py`, `RotationConfig`, UI params route, runtime rotation state updates | listing, runtime strategy resolution, UI summaries | **core active** | Runtime-facing resolved state |

---

## Broker and Live-Safety Fields

| Column | Write paths | Read / logic paths | Classification | Notes |
| --- | --- | --- | --- | --- |
| `broker_type` | migration default; intended manual/operator DB updates | `trading/brokers/factory.py` broker selection | **manual / safety-critical** | Narrow surface, but real runtime behavior |
| `broker_host` | migration add; intended manual/operator DB updates | `trading/brokers/factory.py` live broker connection setup | **manual / safety-critical** | Only used for live broker connectivity |
| `broker_port` | migration add; intended manual/operator DB updates | `trading/brokers/factory.py` live broker connection setup | **manual / safety-critical** | Only used for live broker connectivity |
| `broker_client_id` | migration add; intended manual/operator DB updates | `trading/brokers/factory.py` live broker connection setup | **manual / safety-critical** | Only used for live broker connectivity |
| `live_trading_enabled` | migration default; must be manually enabled by human | broker factory hard gate, evaluation/promotion assessment | **manual / safety-critical** | The most sensitive field in the table; must never be bot-enabled |

---

## Current Takeaways

1. The `accounts` table is **wide but not obviously dead**. Most columns belong to
   active feature families: core account state, trading policy, rotation, and
   live-broker safety.
2. The best cleanup candidates are **not the obvious core fields**. They are more
   likely to be:
   - advanced LEAPs tuning fields that are heavily surfaced but less frequently used
   - display/config-oriented goal fields that may not justify their current breadth
   - any option fields currently marked **unclear / revisit**
3. The broker fields are intentionally narrow. Their limited write surface is a
   feature, not a sign of dead code.

---

## Recommended Follow-up

If this audit is used to drive schema simplification, do it in this order:

1. Revisit the **unclear / revisit** fields (`roll_dte_threshold`,
   `profit_take_pct`, `max_loss_pct`) and confirm whether they affect any live
   execution path beyond config + reporting.
2. Review whether the **goal fields** should remain first-class DB columns or be
   simplified into a smaller operator-metadata surface.
3. Keep the **broker / live-safety** fields intact unless the live-broker model
   itself changes.
