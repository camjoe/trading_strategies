# IBKR Trading Operations Runbook

Type: runbook
Status: Active
Created: 2026-10-09
Last Reviewed: 2026-10-09
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
grep -h "executed\|Market closed\|COMPLETE\|ERROR" local/logs/daily_paper_trading_$(date +%Y%m%d)_*.log
```

| Log line | Meaning |
|---|---|
| `COMPLETE: Daily paper trading run succeeded.` | Every step finished |
| `<account>: executed N trades` | Orders were sent for that account |
| `Market closed: no orders will be submitted` | Completed, but outside market hours |
| `ERROR: Broker session unavailable, no step ran. ...` | A run account's broker could not connect, so nothing ran |

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
| Daily run starts with a session down | Log: `ERROR: Broker session unavailable, no step ran. <account> (<broker type>): ...`; artifact `status: failed`, `failed_step: 00_ingest_market_and_account`; no step runs for any account | `fail`, event `daily-paper-trading`: "Daily paper trading run failed: ..." |
| Any later daily step fails | Log `ERROR:` line; artifact `failed`, with the failed step | `fail`, event `daily-paper-trading` |
| A kill switch is on | Run completes; artifact lists `kill_switch_accounts` | `warn`, event `daily-paper-trading` |
| Daily health check finds the latest log stale or missing the success line | `[FAIL] ...` on its output | `fail`, event `daily-trader-health` |
| Run completes | Success line in the log | none, unless run with `--notify-on-success` |

The keepalive alerts once per change, not once a minute. A start with the session already down alerts;
a healthy start does not.

One unavailable IBKR account stops the whole run, simulator accounts included. If you cannot log in
before a run, set the IBKR account back to `paper` (see Rolling back in
[ibkr-paper-trading.md](ibkr-paper-trading.md)) so the others trade.

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
