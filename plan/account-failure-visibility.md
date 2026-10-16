# Plan: make one account's failure contained and visible

Status: partly done, revised 2026-10-16. PR #296 (`fix/skip-unavailable-ibkr-accounts`) is merged, so read
**DURING #296** below as "a follow-up PR". The guard fix is done. Item B is done (service in
PR #313, health-check wiring after it). Item A is done for broker anomalies (A1). Item E remains. The streak and heartbeat checks (C) and the per-account guard (D) were dropped on 2026-10-16: the warning emails cover the first, and the second adds risk to the guard for little gain.

## Goal
One account failing must not stop the others from trading, and a failure that repeats must get
louder instead of staying a daily email nobody reads. The question that started this: what if an
account keeps failing for a week and nobody notices?

## What exists today (verified in the code, 2026-10-09)
| Failure | What happens | After a week unnoticed |
|---|---|---|
| IBKR session down, before #296 | Step 00 raises; the whole run fails; the 13:00 health check also fails | A `fail` every day, loud |
| IBKR session down, with #296 | The account is skipped and a `warn` names it; the run ends `COMPLETE`; the health check passes | A `warn` every day, never escalating. #296 trades loudness for availability. |
| One account's order submission fails (`broker_api_anomaly`) | `run_auto_trades` finishes its whole cap group, then returns exit 1; `stream_command` raises; the run stops at that step; later cap groups and every later step (snapshots, report) never run | Accounts in later groups trade nothing; the alert says only "Step failed: Auto Trader (...) (exit=1)"; the account name is only in the log |
| An account hits a kill switch | The run completes with a `warn` | The account never trades; a `warn` every day |
| Alerts unconfigured or the transport broken | Nothing | Nothing |

The 13:00 health check (`trader_health.py`) only checks that the latest daily log is recent and carries
`COMPLETE`. It knows nothing about individual accounts.

## Guard fix (decided 2026-10-09) — DONE
Done: `already_completed_for_period` in `job_helpers.py` returns true when any log of the job and day carries
the sentinel, and `already_completed_today` uses it. The text below is the record of the decision.

The multi-lens review of #296 found that the duplicate-run guard reads only the newest log of the
date (`latest_log_contains_sentinel`, `job_helpers.py:176`). A partial run now writes `COMPLETE`; a
failed catch-up run (`--accounts <skipped> --force-run`) then becomes the newest log with no
`COMPLETE`, and a plain run passes the guard and trades the accounts that already traded.

Decision: the date counts as done if **any** of that date's logs carries `COMPLETE`.
- Add an any-log helper next to `latest_log_contains_sentinel`; point `already_completed_today`
  (`paper_trading/__init__.py:66`) at it. The newest-only helper then has no caller; delete it and its
  three tests in `test_job_helpers.py` (the newest-match test encodes the full-run assumption that
  #296 changes).
- `replay_daily_runs` uses the same function; a date with a partial `COMPLETE` was already treated as
  done there, so it does not change.
- Reword `ibkr-operations.md:205` ("so a plain re-run works") and `unavailable_message`
  (`broker_preflight.py:49`): a plain re-run works only if no run completed that day; otherwise run
  the skipped accounts with `--accounts <names> --force-run`.
- Tests: a partial skip leaves `COMPLETE`; a following all-unavailable `--force-run` fails; a plain
  run after that still skips. Plus an any-log helper test and the state tests in
  `test_daily_paper_trading_state.py`.

This is what makes item A1's premise hold ("a plain re-run cannot trade anyone twice").

## Items

### A. Contain a trading-step failure: DONE for broker anomalies (A1)
Done: the group loop in `workflow.py` runs every cap group when an account hits a broker API anomaly.
`run_auto_trades` prints `BROKER_API_ANOMALY_ACCOUNTS: <names>` (constant in `job_helpers.py`) before exiting 1;
`run_auto_trader_group` reads it from the command output and returns the names. The run writes `COMPLETE` and
sends a `warn` naming the accounts and telling the operator to check the broker's open orders before a re-run (no
re-run command is given: a re-run can send an order twice); the artifact carries `broker_anomaly_accounts`. An
anomaly on every account, a crash, or an exit 1 without the line still fails the run.

Left, not built:
- **Per-account containment of unexpected exceptions.** `run_accounts`
  (`src/trading/services/auto_trading/inputs.py`) has no per-account catch, so an exception in one account (market
  data, database) aborts the accounts after it in its group and fails the step. It likely wants a per-account
  result in the same shape as the anomaly.
- **A repeated anomaly never escalates.** The failed account still gets its post-trade snapshot, so item B reads it as
  fresh and a daily anomaly stays a daily `warn`. That is accepted: a repeated warning is read from the emails.
- **Step 08 can still fail the whole run.** One reconcile subprocess covers every account, so a broker error on
  one account stops it.

### E. Surface unresolved orders found by the pre-trade reconcile
Step `01_mark_book_nav` already reconciles every account's open orders before any run trades, so a
partly submitted order has its state applied with no extra broker call. When reconcile leaves orders unresolved
(sent but never confirmed, or open but unreported by the broker), `reconcile_orders.py` only prints a WARNING to
stderr and trading goes on; the artifact and alert never mention it. Report the unresolved counts from that
output in step 01's result and in the run's `warn`, using the same line-parsing approach as item A.

Decided 2026-10-16 (owner): surface only. An unresolved order does not block that account's trading; revisit
blocking if a real warn shows one. Branch `feature/surface-unresolved-orders`, off `develop` once the item A PR is
merged (both change `workflow.py`). Work: `reconcile_orders.py` prints one stable line per account with its
unresolved pending and unreported ids (a constant in `job_helpers.py`, like item A's); step 01's result carries
them; `_finish_run` adds an `unresolved_orders` artifact key and a `warn` note naming the accounts. Tests: a
reconcile with unresolved ids prints the line; the run still completes and warns; a clean reconcile adds nothing.
Docs: the failure table in `ibkr-operations.md`.

### B. Account freshness check: DONE
`evaluate_account_freshness` (PR #313) and its wiring into `trader_health.py` are in. The health check reports one
`account-freshness` digest, takes `--warn-after-weekdays` and `--fail-after-weekdays`, and exits 1 on a `fail`
or when the check cannot run. No exclusion option exists: every account in the database trades daily; add one if
an account is ever left out of the daily job on purpose.

The original design notes follow.

Add to the 13:00 health check a cause-agnostic check: for every account, how many weekdays since its
last equity snapshot. Alert when an account has gone too long without one, as one digest naming the
accounts and their last-seen dates.
- Why this signal: every run snapshots every account it handles, including when the market is closed
  (a Sunday manual run snapshotted). An account that was skipped, never reached, aborted, or dropped by
  a typo goes stale the same way, whatever the cause. No new recording is needed.
- Data: `equity_snapshots` is keyed by `book_id`; join through books to accounts. Add a repository
  read for the latest snapshot time per account. Compare in weekdays, not hours: the job runs Monday
  to Friday even on market holidays.
- Proposed thresholds (UNCONFIRMED, owner to choose): `warn` at 2 weekdays, `fail` at 5. One digest
  alert per run, not one per account. Make both thresholds command-line options.
- Escalation comes free: the message carries the count, which grows each day.
- UNVERIFIED: whether any account is intentionally left out of the scheduled run. The Monday
  scheduled run listed every account, but check `job_schedule.json` for `--accounts` arguments before
  shipping. If one exists, the check needs an exclusion list or it will alert forever.
- Exit code and sentinel logic of the existing check stay as they are; this adds a second result.

Tests: fresh, 2-weekday stale, 5-weekday stale, weekend gap not counted, account with no snapshot ever,
digest names several accounts. Docs: `ibkr-operations.md` (alert table), `runtime-operations.md`.

## Order
1. Guard fix (above) into #296. Then decide A1 or A2 and add item A to #296 (or leave it for a
   follow-up PR if #296 is merged first).
2. Item B on its own branch, off `develop`, once #296 is merged.
3. Item E, once the owner has decided whether an unresolved order blocks that account's trading.

## Constraints
- Layering per `docs/architecture/architecture-conventions.md`. The freshness query belongs in a
  repository and a service, not in the job module.
- Do not touch `live_trading_enabled`, `broker_type`, or the paper-account assertion. Never catch the
  three broker guard errors.
- Comments state facts, not history (`docs/conventions/python-style.md`).

## Acceptance
- A broker error on one account no longer stops the other cap groups, and the alert names it.
- An account that has not been snapshotted for the threshold number of weekdays appears in a daily
  alert with its last-seen date; the alert escalates from `warn` to `fail`.
- `python -m scripts.run_checks pr --base develop` passes, and `pr ready` (the independent reviewers and
  the readiness comment) is run on each PR.

## Hand-off prompt (for a fresh agent)
Read `AGENTS.md`, `docs/architecture/architecture-conventions.md`, and this file in full. Do not start
item A before the owner has chosen A1 or A2. Item B is independent of A: branch off `develop` once
#296 is merged, as `feature/account-freshness-check`. Run `python -m scripts.run_checks quick` after
each step, and stop and report if an UNVERIFIED point turns out false.
