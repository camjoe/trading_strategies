# Plan: name an account that has stopped being snapshotted

Status: drafted 2026-10-15. Not started.
Branch to use: `feature/account-freshness-check`, off `develop`.

## Goal
Report every account whose newest equity snapshot is too many weekdays old, whatever the cause: skipped,
never reached, aborted, or dropped by a typo. The question behind it: what if one account keeps failing for a
week and nobody notices? This plan builds the check as a read-only service with tests. Wiring it into the 13:00
health check is a separate change the owner makes afterwards (see "Not in this plan").

This is item B of `account-failure-visibility.md`, cut down to the part that touches no guarded path.

## Why a snapshot is the signal
Every daily run snapshots every account it handles, including when the market is closed (a Sunday manual run
snapshotted). An account that was skipped, never reached, aborted, or dropped by a typo goes stale the same way,
so no new recording is needed.

## What exists (checked 2026-10-15)
- `EquitySnapshotRepository.fetch_latest(account_id=...)` in `src/trading/repositories/snapshots.py` returns an
  account's newest `EquitySnapshotRecord` or `None`; its `snapshot_time` is a string. No new repository method
  is needed.
- `AccountRepository.fetch_all()` in `src/trading/repositories/accounts.py` lists the accounts.
- `src/trading/services/operations/` holds read-only monitoring services (`job_status.py`, `schedule_status.py`)
  and `tests/src/trading/services/operations/` their tests. The new service goes beside them.
- Nothing checks accounts one by one today: `trader_health.py` only checks that the newest daily log is recent
  and carries `COMPLETE`.

## Scope: unguarded paths only
New files:
- `src/trading/services/operations/account_freshness.py`
- `tests/src/trading/services/operations/test_account_freshness.py`

Edited files: `docs/maps/trading-package-map.md` (a row for the module, beside `operations/job_status.py`; the
maps check fails without it) and `docs/runbooks/runtime-operations.md` (a short section describing the service).

Do not edit anything under `src/trading/interfaces/runtime/jobs/`, including `trader_health.py`. The plan pickup
holds a whole run that touches a guarded path, so one such edit would keep every commit local.

## Design
- `weekdays_since(last: dt.date, as_of: dt.date) -> int`: the number of Monday-to-Friday dates `d` with
  `last < d <= as_of`. Market holidays count as weekdays, because the job runs Monday to Friday regardless.

  | Last snapshot | As of | Result |
  |---|---|---|
  | Friday | Friday (same day) | 0 |
  | Friday | Monday | 1 |
  | Wednesday | Friday | 2 |
  | Friday | next Friday | 5 |
  | Saturday | Monday | 1 |

- `evaluate_account_freshness(accounts, snapshots, *, as_of, warn_after=2, fail_after=5, exclude=())`
  returns a frozen `FreshnessReport` with three lists of `AccountFreshness(account_name, last_snapshot_date,
  weekdays_stale)`:
  - `warn`: stale for `warn_after` weekdays or more, but fewer than `fail_after`;
  - `fail`: stale for `fail_after` weekdays or more;
  - `never`: no snapshot yet. These are reported as their own list and are never a failure, so a new account
    does not alert on its first day.
  An account whose name is in `exclude` is left out of all three. `exclude` defaults to empty.
- The snapshot's date is the UTC date of `snapshot_time`; the caller passes `as_of`. Read the time helpers in
  `src/common/time.py` and parse with them. UNVERIFIED: the exact stored format; read `EquitySnapshotRecord`
  and a test that builds one first.
- The thresholds (warn at 2 weekdays, fail at 5) are PROPOSED defaults for the owner to confirm or change; they
  are plain parameters, so changing them is one line.
- Read-only: no database write, no migration, no new column.

## Steps
1. Read `src/trading/repositories/snapshots.py`, `src/trading/models/portfolio.py` (`EquitySnapshotRecord`),
   `src/common/time.py`, `src/trading/services/operations/job_status.py`, and its test for the fixture style.
2. Write `weekdays_since` and its table test, including a weekend start, a weekend end, and `last > as_of`
   (treat as 0).
3. Write `evaluate_account_freshness` and tests on an in-memory database: fresh, exactly `warn_after`,
   exactly `fail_after`, one under each, a weekend gap that must not count, an account with no snapshot, an
   excluded account, and several stale accounts in one report.
4. Add the map row and the runbook section.
5. Run `python -m scripts.run_checks quick` after each step and `python -m scripts.run_checks pr --base develop`
   at the end.

## Constraints
- Layering per `docs/architecture/architecture-conventions.md`: a service reads through repositories; it opens
  no connection and imports nothing from `interfaces`.
- Do not touch `live_trading_enabled`, `broker_type`, or the paper-account assertion.
- Comments state facts, not history (`docs/conventions/python-style.md`).

## Acceptance
- The table above holds for `weekdays_since`, and the weekend cases are covered by tests.
- A report lists each stale account once, in the right list, with its last snapshot date.
- No file under a guarded path is changed (`python -m scripts.checks.repo.review_scope_check` lists none as
  high risk for this diff).
- `python -m scripts.run_checks pr --base develop` passes.

## Not in this plan (the owner, interactively, after this merges)
- Wire the report into `trader_health.py`: a second result beside the existing log check, one digest alert that
  names the accounts and their last-seen dates, the thresholds as command-line options, and the existing exit
  code and sentinel logic unchanged.
- Check the host's `job_schedule.json` for `--accounts` on the daily job (the repository holds only the example,
  whose daily entry has no arguments) and pass any account left out on purpose as `exclude`, or the check will
  alert on it forever.
- The other items of `account-failure-visibility.md` (A, C, D).

## Hand-off prompt (for a fresh agent)
Read `AGENTS.md`, `docs/architecture/architecture-conventions.md`, and this file in full. Work only in the new
service, its test, and the two docs named under "Scope". Do not edit `trader_health.py` or anything under
`src/trading/interfaces/runtime/jobs/`. Stop and report if an UNVERIFIED point turns out false.
