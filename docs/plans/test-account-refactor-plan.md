# Test Account Refactor Plan

Date: 2026-04-24

## Status
- Completed on 2026-05-02.
- Phase 2 compatibility-retirement goals are complete:
  - canonical persisted manual account identity is `test_account`,
  - legacy `test_account_bt` and `test_shadow` compatibility behavior is retired from production request paths,
  - runtime job exclusions and compare-view behavior are role/canonical driven.

## Summary
- Consolidate `test_account` into one canonical manual-only account policy with a single resolver/service path.
- Keep external alias compatibility: `test_account` remains the UI/API-facing name.
- Exclude this manual account from automated runtime jobs (auto-trades, snapshot batches, scheduled backtest refresh, and similar job-wide "all accounts" paths).
- Keep manual account usable for manual trades and account detail analysis; exclude it from compare-style aggregate views.

## Discovered Code Surface (End-to-End)
- Backend core:
  - `paper_trading_ui/backend/services/test_account.py`
  - `paper_trading_ui/backend/routes/accounts.py`
  - `paper_trading_ui/backend/routes/trades.py`
  - `paper_trading_ui/backend/routes/backtests.py`
  - `paper_trading_ui/backend/routes/actions.py`
  - `paper_trading_ui/backend/routes/admin.py`
  - `paper_trading_ui/backend/routes/analysis.py`
  - `paper_trading_ui/backend/services/accounts/backtests.py`
  - `paper_trading_ui/backend/services/accounts/data_access.py`
  - `paper_trading_ui/backend/account_options.py`
  - `paper_trading_ui/backend/config.py`
- Trading/account model + persistence:
  - `trading/services/accounts/config.py`
  - `trading/services/accounts/queries.py`
  - `trading/services/accounts/__init__.py`
  - `trading/repositories/accounts.py`
  - `trading/database/db_schema.py`
  - `trading/database/db_migrations.py`
- Runtime jobs and account selection:
  - `trading/interfaces/runtime/jobs/daily_paper_trading.py`
  - `trading/interfaces/runtime/jobs/daily_snapshot.py`
  - `trading/interfaces/runtime/jobs/daily_backtest_refresh.py`
  - `trading/interfaces/runtime/jobs/job_helpers.py`
  - `trading/config/account_trade_caps.json`
- Frontend:
  - `paper_trading_ui/frontend/src/lib/constants.ts`
  - `paper_trading_ui/frontend/src/features/admin/test-account.ts`
  - `paper_trading_ui/frontend/src/features/admin/accounts.ts`
  - `paper_trading_ui/frontend/src/features/accounts/detail.ts`
  - `paper_trading_ui/frontend/src/features/admin/types.ts`
  - `paper_trading_ui/frontend/src/views/admin/test-account.html`
  - `paper_trading_ui/frontend/src/views/admin/overview.html`
- Test coverage touchpoints (selected):
  - `tests/paper_trading_ui/backend/services/test_account/test_test_account_service.py`
  - `tests/paper_trading_ui/backend/routes/accounts/test_accounts_routes.py`
  - `tests/paper_trading_ui/backend/routes/trades/test_trades_routes.py`
  - `tests/paper_trading_ui/backend/routes/actions/test_actions_routes.py`
  - `tests/paper_trading_ui/backend/services/accounts/test_backtests.py`
  - `tests/paper_trading_ui/backend/services/accounts/test_data_access.py`
  - `tests/trading/interfaces/runtime/jobs/test_daily_paper_trading_config.py`
  - `tests/trading/services/accounts/test_queries.py`
  - `tests/trading/repositories/test_accounts_repository.py`

## Implementation Changes
- Define one canonical account role model:
  - Introduce a single explicit "manual-only" semantic in account-role policy.
  - Keep backward compatibility by accepting existing legacy role/value(s) during normalization and migration.
- Centralize identity + policy resolution:
  - Add one backend resolver/service responsible for:
    - alias resolution (`test_account` -> persisted manual account),
    - visibility behavior,
    - "manual-trades allowed" policy,
    - "runtime-job eligible" policy.
  - Remove route-level ad hoc checks and per-route name rewrites.
- Remove shadow-account/backtest alias coupling:
  - Retire `test_account` -> `test_account_bt` behavior as the primary mechanism.
  - Replace with direct canonical manual-account lookup.
- Runtime eligibility cleanup:
  - Stop using hard-coded name exclusion as the primary guard (`test_account_bt` in config).
  - Filter by account role in shared account-selection paths used by scheduled jobs.
  - Keep explicit config exclusions as optional operator override, not the core safety mechanism.
- API/interface behavior (non-breaking externally):
  - Keep external alias name `test_account`.
  - Keep manual trade endpoint behavior for that alias.
  - Keep detail + per-account analysis available for the manual account.
  - Exclude manual account from compare-style aggregate outputs.
- Data migration path:
  - Add migration step to classify legacy test-shadow rows into canonical manual-only role.
  - Keep temporary compatibility read path for old values until migration is complete and verified.

## Test Plan
- Backend policy/resolver tests:
  - alias resolution for `test_account`,
  - canonical row lookup,
  - manual-trade eligibility,
  - runtime-job eligibility.
- Route behavior tests:
  - `/api/accounts` includes alias account once,
  - `/api/accounts/{test_account}` detail works,
  - `/api/accounts/{test_account}/analysis` works,
  - `/api/accounts/compare` excludes manual account,
  - manual-trade endpoint accepts alias and rejects non-manual accounts.
- Runtime job tests:
  - `--accounts all` excludes manual-only accounts by role (not by hard-coded account name),
  - explicit `--accounts test_account` behavior validated (error or skip policy, defined once and shared).
- Migration/repository tests:
  - legacy role values normalize correctly,
  - migrated rows preserve safety (`live_trading_enabled = 0`),
  - role-filtered list APIs return expected sets.

## Assumptions and Defaults
- One canonical manual account only.
- External alias name remains `test_account`.
- Legacy aliases/values are migrated in DB init and no longer part of production request behavior.
- Manual account is excluded from automated jobs and aggregate compare views.
- Manual account remains available for manual trade entry and account-detail analysis.

## Phase 2 Re-Plan (Post-Compatibility)
- Purpose:
  - After compatibility rollout is stable, create a new follow-up implementation plan focused on simplifying and removing temporary compatibility paths.
- Trigger / readiness checklist:
  - Legacy compatibility migration is deployed and verified.
  - No unexpected runtime issues from manual-only role filtering.
  - Alias behavior and manual-trade flows are confirmed stable.
- Scope for the follow-up plan:
  - Evaluate hard cutover to a single canonical persisted identity (`test_account`) and remove `test_account_bt` coupling.
  - Remove legacy `test_shadow` compatibility reads/writes and alias fallback branches.
  - Collapse resolver logic to one minimal policy path driven by `account_kind == manual_only`.
  - Simplify affected routes/services/tests accordingly.
- Exit criteria for the follow-up plan:
  - No production code path depends on legacy `test_shadow` values.
  - No production code path requires `test_account_bt` alias mapping behavior.
  - Test suite and docs reflect the simplified canonical-only model.
