# IBKR Trading Operations Runbook

Type: runbook
Status: Active
Created: 2026-10-09
Last Reviewed: 2026-10-18
Purpose: Day-to-day commands to start IB Gateway, its health alert, and the daily trader, confirm each is working, and know what alerts go out when one fails.
Related: [IBKR Paper Trading Runbook](ibkr-paper-trading.md), [Production Runtime Host](production-runtime-host.md), [Runtime Operations](runtime-operations.md), [Runtime Jobs Reference](../reference/runtime-jobs.md)

Operator procedure for a host that trades IBKR paper accounts on a schedule over the socket transport
(`interactive_brokers_socket_paper`). One-time setup lives in
[production-runtime-host.md](production-runtime-host.md) (Part 6, including the units named here); moving
an account onto IBKR lives in [ibkr-paper-trading.md](ibkr-paper-trading.md). Nothing in Part 6 has run
on a host yet; its first-week checks settle what is unverified.

Run the commands from the production checkout with its virtual environment active.

## What runs

| Part | Runs as | Needs |
|---|---|---|
| IB Gateway | the desktop session, started by you | a login on Sunday night; IBKR's auto-restart keeps it logged in through the week (UNVERIFIED on this host) |
| Awake window | system units `trading-awake.service` and its two timers | nothing; holds the host awake Sunday evening to Friday after the close |
| Health alert | system unit `ibkr-gateway-health.service`, bound to the awake window | `.env` for alerts |
| Daily trader | system timer `daily-paper-trading.timer` (weekdays) | a logged-in Gateway when any run account is on IBKR |
| Daily health check | system timer `daily-trader-health-check.timer` (weekdays) | the daily trader's log |

The run times come from the gitignored `job_schedule.json`, which sits beside `src/infrastructure/config/job_schedule.example.json`. Accounts on the `paper`
broker need none of the Gateway pieces; only accounts on `interactive_brokers_socket_paper` do.

## Start

### IB Gateway, weekly

Sunday evening the host wakes by itself. Check the window is open, then log in to IB Gateway on the
host's desktop with the paper login:

```bash
systemctl is-active trading-awake.service ibkr-gateway-health.service
```

```bash
systemd-inhibit --list | grep trading
```

If the Gateway is not running, start it from the desktop. Nothing logs in for you. Until you do, the
health alert sends a `fail` after 15 minutes; log in and it sends `ok`.

Log in again after every host reboot and any alert that says the Gateway is `rejected` or `unreachable`
and does not clear by itself.

### Daily trader

The scheduler starts the trader. Register the timers from the schedule config, then install them:

```bash
python -m trading.interfaces.runtime.scheduling.manage_job_schedules --env-file <repo>/.env
```

```bash
sudo bash local/install_trading_timers.sh
```

A relative `--env-file` path is resolved to an absolute one when the unit is generated, because
systemd ignores a relative `EnvironmentFile=`. Re-run both commands whenever the schedule file
changes.

Run it by hand, for all accounts or for a few:

```bash
python -m trading.interfaces.runtime.jobs.daily.paper_trading --run-source manual
```

```bash
python -m trading.interfaces.runtime.jobs.daily.paper_trading --accounts <name>,<name> --run-source manual
```

A manual run does not load `.env` (only the services and timers do), so it sends alerts only if you
load it first: `set -a; . ./.env; set +a`.

The market must be open for orders to go out. Outside US regular hours the run still completes, and
every account reports `Market closed: no orders will be submitted`.

## Confirm

### IB Gateway

The health worker logs one line per change of state:

```bash
journalctl -u ibkr-gateway-health.service -n 10 --no-pager
```

| Journal line | Meaning |
|---|---|
| `IB Gateway alive` | The API port answers and reports an account |
| `IB Gateway rejected: ...` | The port answers but reports no account, or the client refused |
| `IB Gateway unreachable: ...` | Nothing listens on the API port: stopped, or at its login screen |

Any trouble in the last day:

```bash
journalctl -u ibkr-gateway-health.service --since "24 hours ago" --no-pager | grep -E "rejected|unreachable"
```

For a fuller read-only check of the account, with the client id that is reserved for it:

```bash
python -m scripts.ibkr_socket_smoke_test --port 4002 --client-id 99
```

### Daily trader

The timers are installed and match the schedule file (exit code 0 means in sync):

```bash
python -m trading.interfaces.runtime.scheduling.manage_job_schedules --status
```

When each timer last fired and fires next:

```bash
systemctl list-timers --all | grep -E 'daily-|weekly-'
```

What the last run did:

```bash
journalctl -u daily-paper-trading.service --since today --no-pager | tail -20
```

The run's own log has the detail. Look for the success line and the per-account trade counts:

```bash
grep -h "executed\|Market closed\|COMPLETE\|ERROR\|WARN: skipping" local/logs/daily_paper_trading_$(date +%Y%m%d)_*.log
```

| Log line | Meaning |
|---|---|
| `COMPLETE: Daily paper trading run succeeded.` | Every step finished |
| `<account>: executed N trades` | Orders were sent for that account |
| `Market closed: no orders will be submitted` | Completed, but outside market hours |
| `WARN: skipping <account>, broker session unavailable (...)` | That account was left out; the others traded |
| `RUN META (after skips): accounts=... caps=...` | The accounts and caps the run actually traded, after the skips; the first `RUN META` line lists every requested account |
| `ERROR: Broker session unavailable for every run account, no step ran. ...` | No run account could connect, so nothing ran |

Status of every monitored job in one view:

```bash
python -m scripts.check_jobs
```

Orders on an IBKR account also appear in the Client Portal website and in the account's orders list.
The governance jobs (W1 to W3, M1 to M3) are not scheduled, so `check_jobs` always lists them as not
run.

## When something fails

Alerts go through the webhook and SMTP settings in `.env`, and only when at least one is set. Sending is
best-effort: a delivery failure prints to stderr and never fails the job. See
[runtime-operations.md](runtime-operations.md#runtime-notifications) for the variables.

| Event | What you see | Alert sent |
|---|---|---|
| Gateway down or logged out for 15 minutes | Health journal: `IB Gateway unreachable: ...` | `fail`, event `ibkr-gateway-health`: "IB Gateway unreachable: ... Start IB Gateway and log in." |
| Gateway answers but reports no account for 15 minutes | Health journal: `IB Gateway rejected: ...` | `fail`, same event: "IB Gateway rejected: ... Log in at IB Gateway." |
| Gateway back after an alert | Health journal: `IB Gateway alive` | `ok`: "IB Gateway alive again" |
| Gateway's nightly restart | Journal lines for the outage, if it lasts a poll or two | none, if it ends inside the 15 minutes |
| Daily run starts with some accounts' sessions down (the rest, such as simulator accounts, are fine) | Log: `WARN: skipping <account>, broker session unavailable (<broker type>: <reason>)`; the run trades the other accounts and ends with `COMPLETE`; artifact `skipped_accounts` names the skipped ones. A connect is tried three times, 5 and 15 seconds apart, before the account is skipped | `warn`, event `daily-paper-trading`: "completed without accounts whose IBKR session was unavailable: ... Run them with: <repo .venv python> -m ... --accounts <names> (the run's caps, fee, seed and date carried over) --run-source manual --force-run" |
| Daily run starts with every account's session down | Log: `ERROR: Broker session unavailable for every run account, no step ran. <account> (<broker type>: <reason>)`; artifact `status: failed`, `failed_step: 00_ingest_market_and_account`, `skipped_accounts` naming every account and why (the run failed; none traded) | `fail`, event `daily-paper-trading`: "Daily paper trading run failed: ..." |
| Any later daily step fails | Log `ERROR:` line; artifact `failed`, with the failed step | `fail`, event `daily-paper-trading` |
| A kill switch is on | Run completes; artifact lists `kill_switch_accounts` | `warn`, event `daily-paper-trading` |
| Daily health check finds the latest log stale or missing the success line | `[FAIL] ...` on its output | `fail`, event `daily-trader-health` |
| Run completes | Success line in the log | none, unless run with `--notify-on-success` |

The health alert sends once per failure and once on recovery, not once per poll. A Gateway still down
after the grace period at the start of the week alerts; a healthy start does not.

An account whose broker session is unavailable is skipped; the others still trade. A run that skips
any account still ends with `COMPLETE`, so the duplicate-run guard stops a plain second run that day.
After you fix the session, run the skipped accounts with `--accounts <names> --force-run` (the `warn`
alert prints the command). `--accounts` limits the run to those accounts, so nothing else trades twice.
A run in which every account is unavailable fails and writes no `COMPLETE`, but the guard counts the
date as done if any of that date's logs has `COMPLETE`, so a plain re-run works only when no run
completed that day. While an account is skipped, nothing reconciles its fills or snapshots its equity;
its books catch up when you run it.

### What sends nothing

- **The host is off or asleep.** No timer fires and the health check does not run either, so no alert
  is sent. Check `systemctl list-timers`, `systemd-inhibit --list`, and the log dates; the first-week
  checks in Part 6.6 of the host runbook cover a host that sleeps through the window.
- **No transport is configured.** With no webhook and no SMTP settings, every failure above is
  visible only in the journal, the log, and `check_jobs`.
- **A timer is not installed.** `manage_job_schedules --status` reports `MISSING`; nothing alerts.
- **The health service is dead and does not come back.** systemd restarts it after 30 seconds on
  failure. A service that stays failed sends no alert; `systemctl is-active ibkr-gateway-health.service`
  shows it.
- **Alert delivery fails.** The error goes to stderr, in the journal.

### Recovering

1. Fix the cause: start IB Gateway and log in on the host's desktop.
2. Check the Gateway with `python -m scripts.ibkr_socket_smoke_test --port 4002 --client-id 99`.
3. Re-run the trader if the market is still open. If a day was missed, backfill it with
   `replay_daily_runs` (see [runtime-operations.md](runtime-operations.md#run-did-not-execute-scheduler-missed)).
