# IBKR Trading Operations Runbook

Type: runbook
Status: Active
Created: 2026-10-09
Last Reviewed: 2026-10-17
Purpose: Day-to-day commands to start the IBKR gateway, session keepalive, and daily trader, confirm each is working, and know what alerts go out when one fails.
Related: [IBKR Paper Trading Runbook](ibkr-paper-trading.md), [Production Runtime Host](production-runtime-host.md), [Runtime Operations](runtime-operations.md), [IBKR Client Portal Gateway Setup](../reference/broker-setup-ibkr.md), [Runtime Jobs Reference](../reference/runtime-jobs.md)

Operator procedure for a host that trades IBKR paper accounts on a schedule. One-time setup lives in
[production-runtime-host.md](production-runtime-host.md) (Part 6 for the gateway and keepalive units);
moving an account onto IBKR lives in [ibkr-paper-trading.md](ibkr-paper-trading.md).

Run the commands from the production checkout with its virtual environment active. `<user>` is the
login that owns the user services.

## What runs

| Part | Runs as | Needs |
|---|---|---|
| Client Portal Gateway | user service `ibkr-gateway.service` | Java; a manual login after every start or reset |
| Session keepalive | user service `ibkr-keepalive.service` | the gateway; `.env` for alerts |
| Daily trader | system timer `daily-paper-trading.timer` (weekdays) | a logged-in session when any run account is on IBKR |
| Daily health check | system timer `daily-trader-health-check.timer` (weekdays) | the daily trader's log |

The run times come from the gitignored `job_schedule.json`, which sits beside `src/infrastructure/config/job_schedule.example.json`. Accounts on the `paper`
broker need none of the gateway pieces; only accounts on `interactive_brokers_web_paper` do.

## Start

### Gateway and keepalive

Start both and keep them running after logout and across reboots:

```bash
systemctl --user enable --now ibkr-gateway.service ibkr-keepalive.service
```

```bash
loginctl enable-linger <user>
```

Then log in. Nothing logs in for you:

1. Open `https://localhost:5000` in a browser on the host.
2. Sign in with the IBKR **paper** login.

Log in again after every host reboot, every forced IBKR reset, and any alert that says the session is
`rejected`. The keepalive notices the login on its next poll; do not restart it.

Stop or restart them:

```bash
systemctl --user restart ibkr-gateway.service ibkr-keepalive.service
```

```bash
systemctl --user stop ibkr-keepalive.service ibkr-gateway.service
```

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

### Gateway and keepalive

Both services are up:

```bash
systemctl --user is-active ibkr-gateway.service ibkr-keepalive.service
```

`active` means the process runs. It does not mean you are logged in. Check the session itself:

```bash
curl -sk https://localhost:5000/v1/api/iserver/auth/status
```

`"authenticated":true` means the session is good. For a fuller read-only check of the account:

```bash
python -m scripts.ibkr_web_api_smoke_test
```

The keepalive logs one line per change of state. The latest lines show the current state:

```bash
journalctl --user -u ibkr-keepalive.service -n 10 --no-pager
```

| Journal line | Meaning |
|---|---|
| `IBKR session alive` | Logged in and holding |
| `IBKR session rejected: ...` | The gateway answers but you are not logged in |
| `IBKR session unreachable: ...` | Nothing listens on the gateway port |

Any trouble in the last day:

```bash
journalctl --user -u ibkr-keepalive.service --since "24 hours ago" --no-pager | grep -E "rejected|unreachable"
```

The time of the first `rejected` line after a good login shows when IBKR forces a re-login on your
account.

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
| Session lost (gateway answers, not logged in) | Keepalive journal: `IBKR session rejected: ...` | `fail`, event `ibkr-session-keepalive`: "IBKR session rejected: ... Log in at the Client Portal gateway." |
| Gateway down | Keepalive journal: `IBKR session unreachable: ...`; the gateway service restarts it after 30 seconds, logged out | `fail`, same event: "IBKR session unreachable: ... Start the Client Portal gateway and log in." |
| Session back after either | Keepalive journal: `IBKR session alive` | `ok`: "IBKR session alive again" |
| Daily run starts with some accounts' sessions down (the rest, such as simulator accounts, are fine) | Log: `WARN: skipping <account>, broker session unavailable (<broker type>: <reason>)`; the run trades the other accounts and ends with `COMPLETE`; artifact `skipped_accounts` names the skipped ones | `warn`, event `daily-paper-trading`: "completed without accounts whose IBKR session was unavailable: ... Run them with: <repo .venv python> -m ... --accounts <names> (the run's caps, fee, seed and date carried over) --run-source manual --force-run" |
| Daily run starts with every account's session down | Log: `ERROR: Broker session unavailable for every run account, no step ran. <account> (<broker type>: <reason>)`; artifact `status: failed`, `failed_step: 00_ingest_market_and_account`, `skipped_accounts` naming every account and why (the run failed; none traded) | `fail`, event `daily-paper-trading`: "Daily paper trading run failed: ..." |
| Any later daily step fails | Log `ERROR:` line; artifact `failed`, with the failed step | `fail`, event `daily-paper-trading` |
| A kill switch is on | Run completes; artifact lists `kill_switch_accounts` | `warn`, event `daily-paper-trading` |
| Daily health check finds the latest log stale or missing the success line | `[FAIL] ...` on its output | `fail`, event `daily-trader-health` |
| Run completes | Success line in the log | none, unless run with `--notify-on-success` |

The keepalive alerts once per change, not once a minute. A start with the session already down alerts;
a healthy start does not.

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
  is sent. Check `systemctl list-timers` and the log dates.
- **No transport is configured.** With no webhook and no SMTP settings, every failure above is
  visible only in the journal, the log, and `check_jobs`.
- **A timer is not installed.** `manage_job_schedules --status` reports `MISSING`; nothing alerts.
- **The keepalive service is dead and does not come back.** systemd restarts it after 30 seconds on
  failure. A service that stays failed sends no alert; `systemctl --user is-active` shows it.
- **Alert delivery fails.** The error goes to stderr, in the journal.

### Recovering

1. Fix the cause: start the gateway, or log in at `https://localhost:5000`.
2. Check the session with `curl -sk https://localhost:5000/v1/api/iserver/auth/status`.
3. Re-run the trader if the market is still open. If a day was missed, backfill it with
   `replay_daily_runs` (see [runtime-operations.md](runtime-operations.md#run-did-not-execute-scheduler-missed)).

## Socket transport (IB Gateway)

For accounts on `interactive_brokers_socket_paper`. One-time setup, including the units named here, is
[Part 7 of the host runbook](production-runtime-host.md#part-7--ib-gateway-the-weekday-awake-window-and-the-health-alert).
The Client Portal Gateway and keepalive above are not used for these accounts.

| Part | Runs as | Needs |
|---|---|---|
| IB Gateway | the desktop session, started by you | a login on Sunday night; IBKR's auto-restart keeps it logged in through the week (UNVERIFIED on this host) |
| Awake window | system units `trading-awake.service` and its two timers | nothing; holds the host awake Sunday evening to Friday after the close |
| Health alert | system unit `ibkr-gateway-health.service`, bound to the awake window | `.env` for alerts |
| Daily trader | `daily-paper-trading.timer`, as above | a logged-in Gateway when any run account is on the socket |

### Weekly start

Sunday evening the host wakes by itself. Check the window is open, then log in to IB Gateway on the
host's desktop with the paper login:

```bash
systemctl is-active trading-awake.service ibkr-gateway-health.service
```

```bash
systemd-inhibit --list | grep trading
```

If the Gateway is not running, start it from the desktop. Until you log in, the health alert will send a
`fail` after 15 minutes; log in and it sends `ok`.

### Confirm

The health worker logs one line per change of state:

```bash
journalctl -u ibkr-gateway-health.service -n 10 --no-pager
```

| Journal line | Meaning |
|---|---|
| `IB Gateway alive` | The API port answers and reports an account |
| `IB Gateway rejected: ...` | The port answers but reports no account, or the client refused |
| `IB Gateway unreachable: ...` | Nothing listens on the API port: stopped, or at its login screen |

For a fuller read-only check of the account, with the client id that is reserved for it:

```bash
python -m scripts.ibkr_socket_smoke_test --port 4002 --client-id 99
```

### When something fails

| Event | What you see | Alert sent |
|---|---|---|
| Gateway down or logged out for 15 minutes | Health journal: `IB Gateway unreachable: ...` | `fail`, event `ibkr-gateway-health`: "IB Gateway unreachable: ... Start IB Gateway and log in." |
| Gateway answers but reports no account for 15 minutes | Health journal: `IB Gateway rejected: ...` | `fail`, same event: "IB Gateway rejected: ... Log in at IB Gateway." |
| Gateway back after an alert | Health journal: `IB Gateway alive` | `ok`: "IB Gateway alive again" |
| Gateway's nightly restart | Journal lines for the outage, if it lasts a poll or two | none, if it ends inside the 15 minutes |
| Daily run with an account's Gateway down | the same `WARN: skipping <account>, broker session unavailable (...)` as above; a connect is tried three times, 5 and 15 seconds apart, before the account is skipped | `warn`, event `daily-paper-trading`, as above |
| The host went to sleep during the window | no journal lines for the gap; check `systemd-inhibit --list` and the first-week checks in Part 7.6 | none |
