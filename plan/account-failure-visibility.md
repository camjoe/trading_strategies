# Plan: make one account's failure contained and visible

Status: drafted 2026-10-09. Not started. Timing is marked per item against PR #296
(`fix/skip-unavailable-ibkr-accounts`, open): **DURING #296** means add it to that branch;
**AFTER #296** means a separate branch, merged soon after #296.

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

## Items

### A. Contain a trading-step failure — DURING #296
Run every cap group even if one fails, and name the accounts that failed. Same family and same file as
#296 (`workflow.py`); reuses its mechanics (drop or flag the account, `warn`, the duplicate-run guard).

**Decision pending (owner):** how does the run end when a group failed but the others completed?
- **A1 (recommended).** Write `COMPLETE` and send a `warn` that names the failed accounts and the re-run
  command (`--accounts <names> --run-source manual --force-run`), as #296 does for skipped accounts.
  A plain re-run cannot trade anyone twice. Cost: the run looks complete to the health check, so the
  `warn` carries the signal. Item B is the escalation.
- **A2.** Exit 1 and write no `COMPLETE`, but still run the other groups and the snapshots. Louder. Cost:
  a plain re-run would trade the accounts that already traded.

Work:
1. The auto-trade worker must report which accounts hit an anomaly in a form the workflow can read,
   not only in a printed sentence. Options: a machine-readable line the workflow parses, or the
   worker writing a small result file. UNVERIFIED which is simpler; read `run_auto_trader_group` and
   `stream_command` first.
2. In the group loop, catch a group failure, record the failed accounts, and continue with the next
   group and the later steps.
3. Carry the failed accounts into the artifact and the alert, next to `skipped_accounts`.
4. A group failure can leave an account partially submitted. The re-run command must say that the next
   run's reconcile applies any fills first. Check the order of steps before writing that sentence.

Tests: a group fails and the later group still trades; the failed accounts appear in the artifact and
alert; all groups failing still ends the run as a failure; the guard errors still stop everything.
Docs: the failure table and the "When something fails" section in `ibkr-operations.md`.

### B. Account freshness check — AFTER #296, soon
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

### C. Not covered by B — separate, later
- **Kill-switch streaks.** A kill-switched account still snapshots, so B misses it. A streak of
  consecutive runs with a kill switch could be read from the per-run risk snapshots. Decide whether it
  is worth a check once A and B are in.
- **Heartbeat / dead-man's switch** to something outside the host, for "the host stopped sending
  anything". No check on the host can see that. A separate project.

## Order
1. Decide A1 or A2, then add item A to #296 (or leave it for a follow-up PR if #296 is merged first).
2. Item B on its own branch, off `develop`, once #296 is merged.
3. Revisit C.

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
- `python -m scripts.run_checks quick` passes; the multi-lens review in `review-mindsets.md` is run on
  each PR.

## Hand-off prompt (for a fresh agent)
Read `AGENTS.md`, `docs/architecture/architecture-conventions.md`, and this file in full. Do not start
item A before the owner has chosen A1 or A2. Item B is independent of A: branch off `develop` once
#296 is merged, as `feature/account-freshness-check`. Run `python -m scripts.run_checks quick` after
each step, and stop and report if an UNVERIFIED point turns out false.
