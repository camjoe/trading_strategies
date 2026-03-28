# Runtime Job Coverage Follow-Up

Purpose: capture the current low-coverage review so the work can be resumed later without re-auditing the repo.

## Why This Matters

The repository is green overall, but the lowest-coverage areas are now concentrated in operational runtime job modules. That is a different risk profile than low coverage in pure helpers or visualization code.

These files coordinate scheduler-facing behavior, subprocess execution, log/sentinel checks, backup orchestration, and trade-run safety guards. Regressions here are more likely to surface in production-like runs than in day-to-day local development.

## Highest-Priority Gaps

1. `trading/interfaces/runtime/jobs/daily_paper_trading.py`
   - Current concern: effectively untested orchestration path.
   - Why it matters: owns duplicate-run suppression, account selection, trade-cap config parsing, grouped auto-trader invocation, snapshot invocation, compare-strategies invocation, and success/failure log handling.
   - Suggested test targets:
     - `parse_account_trade_caps(...)`
     - `load_trade_caps_config(...)`
     - `resolve_trade_caps(...)`
     - `already_completed_today(...)`
     - `main()` success path with monkeypatched `stream_command`
     - `main()` validation failures for bad min/max and unknown accounts

2. `trading/interfaces/runtime/jobs/check_daily_trader_health.py`
   - Current concern: no direct coverage on health-check branches.
   - Why it matters: this is the operational signal for whether daily trading completed successfully.
   - Suggested test targets:
     - no logs found
     - unreadable latest log
     - stale latest log
     - latest log missing sentinel
     - healthy latest log
     - JSON and plain-text output modes

3. `trading/interfaces/runtime/jobs/register_weekly_backup.py`
   - Current concern: no direct coverage on OS-specific command construction.
   - Why it matters: quoting and command-shape regressions would only show up when registering tasks.
   - Suggested test targets:
     - `validate_day(...)`
     - `validate_time(...)`
     - Windows scheduler command produced by `windows_register(...)`
     - Linux cron line produced by `linux_register(...)`
     - dry-run behavior
     - unsupported OS branch in `main()`

4. `trading/interfaces/runtime/jobs/weekly_db_backup.py`
   - Current concern: no direct coverage on duplicate-week guard and subprocess backup flow.
   - Why it matters: backup scheduling is safety-critical even if it runs infrequently.
   - Suggested test targets:
     - `week_tag(...)`
     - `already_completed_this_week(...)`
     - skip path when current week already completed
     - successful backup subprocess path
     - failing backup subprocess path

## Lower-Priority Gaps

These are worth covering, but they are less urgent than the runtime jobs above.

1. `trends/charts.py`
   - Test deterministic chart-path generation and save behavior.

2. `trends/indicators.py`
   - Add tests for:
     - `calculate_bollinger_bands(...)`
     - `calculate_annualized_volatility_pct(...)`
     - `print_indicator_explanations()`

3. `trends/tickers.py`
   - Add tests for:
     - unknown category error branch
     - default `trends/assets/run_tickers.txt` fallback branch
     - final default `['AAPL']` fallback

4. `trading/database/admin.py`
   - Core destructive paths already have meaningful tests.
   - Remaining gaps are mostly parser/listing/output paths, so this is a cleanup target rather than an immediate operational risk.

## Recommended Work Order

1. Add tests for `daily_paper_trading.py`.
2. Add tests for `check_daily_trader_health.py`.
3. Add tests for `weekly_db_backup.py` and `register_weekly_backup.py`.
4. Add small deterministic tests for `trends/charts.py`, `trends/indicators.py`, and `trends/tickers.py`.

## Ready-To-Use Prompt

Use the prompt below when ready to pick this back up:

```text
Review and improve low-coverage operational modules in this repo, starting with runtime job coverage.

Context:
- The repo is currently green: full pytest, mypy, ruff, docs freshness, and ci_smoke all pass.
- Canonical runtime job modules live under trading/interfaces/runtime/jobs/.
- The highest-priority low-coverage files are:
  1. trading/interfaces/runtime/jobs/daily_paper_trading.py
  2. trading/interfaces/runtime/jobs/check_daily_trader_health.py
  3. trading/interfaces/runtime/jobs/register_weekly_backup.py
  4. trading/interfaces/runtime/jobs/weekly_db_backup.py
- Lower-priority follow-up files are:
  1. trends/charts.py
  2. trends/indicators.py
  3. trends/tickers.py
  4. trading/database/admin.py

Instructions:
- First inspect current tests and coverage gaps before editing.
- Prioritize operational risk over raw percentage improvement.
- Add focused tests, not broad refactors, unless a small refactor is needed to make the code testable.
- Preserve runtime behavior and public CLI/module entrypoints.
- After changes, run:
  1. python -m pytest -o addopts="" tests/trading tests/trends
  2. python -m mypy trading paper_trading_ui/backend --python-version 3.12 --ignore-missing-imports --follow-imports=skip
  3. python -m scripts.check_docs_freshness --repo-root .
- Report which low-coverage branches were actually exercised by the new tests and call out any remaining notable gaps.
```

## Completion Goal

The goal is not just a higher coverage number. The goal is to reduce operational risk in scheduler-facing and automation-facing code while keeping the current architecture stable.