# Production Runtime Host Setup & Deployment Runbook

Type: runbook
Status: Draft
Created: 2026-06-27
Last Reviewed: 2026-10-17
Purpose: Step-by-step setup of the recommended dedicated Linux runtime host and the ongoing test-and-deploy workflow that promotes code to it.
Related: [IBKR Operations Runbook](ibkr-operations.md), [IBKR Paper Trading Runbook](ibkr-paper-trading.md), [Production Runtime Hosting ADR](../adr/008-production-runtime-hosting-and-deployment.md), [Runtime Operations Runbook](runtime-operations.md), [Runtime Jobs Reference](../reference/runtime-jobs.md), [Branching](../conventions/branching.md), [DB Migration System](../reference/db-migration-system.md)

This runbook implements the project's recommended deployment model from
[ADR 008](../adr/008-production-runtime-hosting-and-deployment.md): one dedicated Linux host runs the
scheduled jobs from a production checkout that tracks `main`, development happens elsewhere, and
every deploy passes a pre-deploy test gate. Read the ADR first for the *why* (including why blue/green
is deferred). Adapt the placeholders and optional host-management choices below to the installation.

Conventions used below (adjust to your host):

| Placeholder | Meaning | Example |
|---|---|---|
| `<user>` | Login user on the Linux host | `trading` |
| `~/trading-prod` | Production checkout (tracks `main`, scheduled jobs run from here) | `/home/<runtime-user>/trading-prod` |
| `~/trading-staging` | Optional staging checkout (tracks `develop`, no scheduler) | `/home/<runtime-user>/trading-staging` |

Set `<repository-url>` to the HTTPS or SSH clone URL for the repository.

---

## Part 1 — One-time host setup

### 1.1 Base system

1. Install system packages: `git`, a Python matching `pyproject.toml`'s `requires-python`
   (**currently `>=3.14`**), the matching `python3-venv`, and a C toolchain for any wheels that build
   from source:
   ```bash
   sudo apt update && sudo apt install -y git python3 python3-venv build-essential
   ```
   > Python 3.14 is new — if your distro's default `python3` is older, install 3.14 via the deadsnakes
   > PPA or pyenv and use that interpreter to create the venv in §1.2. Verify with `python3 --version`.
2. **Set the timezone** — OS schedulers fire on local time, so this must match the timezone your
   schedule times assume:
   ```bash
   timedatectl                       # check current
   sudo timedatectl set-timezone America/New_York   # set to your market timezone
   ```
3. **Sleep/suspend.** Choose one of two approaches (decision recorded in Part 5):
   - **Always-on (simpler):** Disable sleep so the host never misses a job:
     ```bash
     sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
     ```
     On a laptop lid also set `HandleLidSwitch=ignore` in `/etc/systemd/logind.conf`, then
     `sudo systemctl restart systemd-logind`.
   - **Suspend+wake (power-saving):** Keep auto-suspend enabled and rely on `WakeSystem=yes` in
     the systemd timer units (§1.5) to wake the machine before each job. Extend the AC inactivity
     timeout to at least 60 minutes so jobs finish before the machine re-suspends:
     ```bash
     gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-timeout 3600
     ```
4. Configure unattended security updates to **not** auto-reboot during market hours (or schedule any
   reboot window outside them). This is the Linux analogue of the Windows-update problem we are
   leaving behind.

### 1.2 Production checkout + venv

```bash
git clone <repository-url> ~/trading-prod
cd ~/trading-prod
git checkout main
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-base.txt   # runtime-only deps (no test deps needed in prod)
python -m pip install -e . --no-build-isolation  # expose src/ and apps/ packages
```

Interactive commands below assume this environment is active. Activate it again after opening a
new shell. Scheduler and wrapper configuration still uses an explicit interpreter path because it
runs without an activated shell.

### 1.3 Secrets and configuration

Copy the committed template and fill in real values:

```bash
cd ~/trading-prod
cp .env.example .env        # .env is gitignored
$EDITOR .env                # set TRADING_IBKR_WEB_API_ACCOUNT_ID, runtime notifications, etc.
chmod 600 .env              # readable only by the runtime user
```

> **Secrets policy (deterministic).** Create the real `.env` **only on this production host**, never
> in a dev checkout where coding agents run. `.gitignore` stops a file from being *committed* — it does
> **not** stop an agent or tool from *reading* it. The protection that actually works is the secrets
> not existing on the machine where agents operate. Keep `.env` mode `600` owned by the runtime user,
> and do not run coding agents on this host. (Optional defense in depth on the dev machine: a Claude
> Code `permissions.deny` read rule for `**/.env` and secret paths.)

**Important — the runtime jobs do not auto-load `.env`.** Unlike the web backend (which loads its
own dotenv file from the committed `apps/paper_trading_web/backend/.env.example` template), the job
entrypoints read `os.environ` directly.
Choose one of the approaches below to get secrets into each job's environment.

#### Approach A — systemd `EnvironmentFile` (recommended for systemd setups)

Pass `--env-file` when registering schedules. The installer adds `EnvironmentFile=-<path>` to each
generated service unit, so systemd loads the file automatically at job launch. The `-` prefix means
a missing file is silently ignored rather than failing the job:

```bash
python -m trading.interfaces.runtime.scheduling.manage_job_schedules \
    --env-file /home/<user>/trading-prod/.env
```

Set the run times in the gitignored `job_schedule.json` under `src/infrastructure/config/` first
(see [runtime-jobs.md](../reference/runtime-jobs.md#the-schedule-config)). Record host-specific
values in `local/operations/production-host-checklist.md`.

Secrets stay in `.env` on disk, mode `600`. Only systemd reads them at runtime — they are never
embedded in the unit files or any logs.

#### Approach B — `run-job.sh` wrapper (for cron setups, or if EnvironmentFile is not available)

Create a tiny shell wrapper at `~/trading-prod/run-job.sh`. It sources `.env` and then
forwards all arguments to the venv Python, so every job it launches inherits the full environment:

```bash
#!/usr/bin/env bash
# run-job.sh — sources .env then delegates to the venv python.
# Pass --python /path/to/run-job.sh to manage_job_schedules so cron jobs inherit secrets.
set -euo pipefail
cd "$(dirname "$0")"
set -a && . ./.env && set +a
exec ./.venv/bin/python "$@"
```

```bash
chmod +x ~/trading-prod/run-job.sh
```

Register with `--python /home/<user>/trading-prod/run-job.sh` instead of the venv python directly:

```bash
python -m trading.interfaces.runtime.scheduling.manage_job_schedules \
    --python /home/<user>/trading-prod/run-job.sh \
    --scheduler cron
```

Every cron line then runs through the wrapper, which loads `.env` before handing off to Python.

#### Approach C — inline vars in crontab (quick / no wrapper)

Declare vars at the top of the crontab above the generated lines:

```
TRADING_RUNTIME_ALERT_WEBHOOK_URL=https://...
TRADING_IBKR_WEB_API_ACCOUNT_ID=...
```

Least preferred — secrets end up visible in `crontab -l` output.

At minimum set:
- Runtime notifications so missed/failed runs are visible: either `TRADING_RUNTIME_ALERT_WEBHOOK_URL`
  or the SMTP variables documented in
  [runtime-operations.md](runtime-operations.md#runtime-notifications).
- `TRADING_IBKR_WEB_API_ACCOUNT_ID` (required) — configure the rest of the IBKR connection per
  [broker-setup-ibkr.md](../reference/broker-setup-ibkr.md).

### 1.4 Seed the database

- SQLite lives under `local/` (gitignored). Either copy the current paper-trading DB from the old
  host into the same relative path under `~/trading-prod/`, or initialize fresh and run migrations.
- Confirm migrations are current (see [db-migration-system.md](../reference/db-migration-system.md)).

### 1.5 Register the schedule (systemd timers)

First set the run times. Copy `src/infrastructure/config/job_schedule.example.json` to
`job_schedule.json` beside it (gitignored) and set real times, days, and the enabled flags (see
[runtime-jobs.md](../reference/runtime-jobs.md#the-schedule-config)).

`manage_job_schedules` reads that file, auto-detects systemd on Linux, and generates systemd timer +
service units with `WakeSystem=yes`, so the machine wakes from sleep before each job fires. It writes
a sudo-ready install script to `local/install_trading_timers.sh`. Run from `~/trading-prod`.
**Always `--dry-run` first:**

```bash
cd ~/trading-prod
python -m trading.interfaces.runtime.scheduling.manage_job_schedules --dry-run
```

Re-run without `--dry-run` to generate the install script, then apply it:

```bash
python -m trading.interfaces.runtime.scheduling.manage_job_schedules
sudo bash ~/trading-prod/local/install_trading_timers.sh
```

See the [Runtime Jobs Reference](../reference/runtime-jobs.md#registering-schedules) for the config
format and every available job. Verify timers are active:

```bash
systemctl list-timers --all | grep -E 'daily-|weekly-'
```

Unit names drop the `Trading\` prefix and hyphenate, so only `daily-paper-trading.timer` contains
"trading" — filtering on that alone hides `daily-challenger-shadow-eval.timer`,
`daily-trader-health-check.timer`, and `weekly-db-backup.timer`. Check that every entry you
registered is listed, not just the daily run.

### 1.6 Verify end to end

```bash
cd ~/trading-prod
# Confirm the runtime can import, read its environment, and inspect recent artifacts:
python -m trading.interfaces.runtime.jobs.daily.trader_health
python -m trading.interfaces.runtime.jobs.maintenance.burn_in_status --force-run
```

The health check also reads the database. On a fresh deploy every account is "never snapshotted", which
prints `[WARN]`, exits 0, and sends an `account-freshness` alert; a database behind the schema head prints
`[FAIL] Account freshness check could not run: ...` and exits 1.

Then confirm monitoring per [runtime-operations.md](runtime-operations.md): logs land in `local/logs/`,
artifacts in `local/exports/`, and `python -m scripts.check_jobs` summarizes status.

---

## Part 2 — Ongoing deploy workflow

The rule from [ADR 008](../adr/008-production-runtime-hosting-and-deployment.md): **the scheduler only
ever runs promoted `main` code from a checkout no one edits.** Development never touches the host
directly.

### 2.1 Develop (on the dev machine)

1. Branch off `develop` (`features/…`, `fix/…`, `refactor/…` per
   [branching.md](../conventions/branching.md)).
2. Do the work; open a PR into `develop`.

### 2.2 Pre-deploy test gate (must pass before promoting)

Run on the dev machine against the change you intend to ship:

```bash
# Full CI-profile checks (layer + lint + type + tests)
python -m scripts.run_checks ci
# Targeted suites for the areas you touched (faster signal)
python -m scripts.checks.run_suite --base develop
```

For a risky change, also smoke it in the **staging checkout** (Part 3) against a copy of the
production DB before promoting.

### 2.3 Promote to `main`

Merge `develop` → `main` via PR (the release/promotion step in
[branching.md](../conventions/branching.md)). This PR merge *is* the deploy authorization.

### 2.4 Pull onto the production host

```bash
cd ~/trading-prod
git fetch origin
git status                 # confirm clean working tree, on main
git pull origin main
# If dependencies changed:
./.venv/bin/pip install -r requirements-base.txt
./.venv/bin/pip install -e . --no-build-isolation
# If a DB migration shipped: apply it (see db-migration-system.md)
# A code-only change needs nothing more — the scheduler runs `python -m <module>`, so the
# next scheduled run loads the new code. Re-register only when the schedule set, times, args,
# or interpreter path change (see runtime-jobs.md "When a reinstall is needed").
```

If the schedule set or times changed, edit the gitignored `job_schedule.json` in
`src/infrastructure/config/` and re-apply. The apply reads that file by default, removes disabled or
absent jobs, and registers the rest, so the host matches the file:

```bash
cd ~/trading-prod
python -m trading.interfaces.runtime.scheduling.manage_job_schedules --dry-run
python -m trading.interfaces.runtime.scheduling.manage_job_schedules
# systemd generates local/install_trading_timers.sh; apply it:
sudo bash ~/trading-prod/local/install_trading_timers.sh
```

### 2.5 Post-deploy verification

```bash
cd ~/trading-prod
# Confirm the registered schedules match the config (exit 0 = in sync):
python -m trading.interfaces.runtime.scheduling.manage_job_schedules --status
python -m trading.interfaces.runtime.jobs.daily.trader_health
python -m scripts.check_jobs
```

The health check also reads the database; see the expected output in 1.6.

Watch the next scheduled run complete (look for the `COMPLETE` sentinel per
[runtime-operations.md](runtime-operations.md)).

---

## Part 3 — Optional staging checkout (pre-deploy smoke test)

A lightweight stand-in for blue/green (see [ADR 008 §4](../adr/008-production-runtime-hosting-and-deployment.md#decision)).
It has **no scheduler**, so it never trades automatically. Use it for deterministic checks and
manual smoke tests against a copy of production state.

```bash
git clone <repository-url> ~/trading-staging
cd ~/trading-staging
git checkout develop
python3 -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt    # dev deps so you can run tests here too
# Use a COPY of the prod DB, never the live file (local/ is gitignored, so create it first):
mkdir -p ~/trading-staging/local
cp ~/trading-prod/local/paper_trading.db ~/trading-staging/local/paper_trading.db
```

Smoke a candidate before promoting:

```bash
cd ~/trading-staging
git pull origin develop
python -m scripts.run_checks ci
python -m trading.interfaces.runtime.jobs.daily.trader_health
python -m trading.interfaces.runtime.jobs.maintenance.burn_in_status --force-run
```

The health check also reads the database; a staging database with no snapshots warns (see 1.6).

Do not run `daily.paper_trading` from staging with real broker credentials unless you intentionally
want a paper-broker execution test. The job has no `--dry-run` flag.

---

## Part 4 — Rollback

No hot standby (by design — ADR 008 §4). Rollback is a git checkout, plus DB restore only if data was
affected:

```bash
cd ~/trading-prod
git log --oneline -n 10            # find the last-good commit
git checkout <good-sha>            # detached HEAD on the known-good code
./.venv/bin/pip install -r requirements-base.txt   # if deps differ
./.venv/bin/pip install -e . --no-build-isolation
# If the bad deploy corrupted data, restore from the weekly backup:
#   see runtime-operations.md "Weekly database backup"
```

Once the fix is ready, ship it forward through the normal gate (do not leave production on a detached
HEAD long-term — return to `main` after `main` carries the fix).

---

## Part 5 — Keeping the host running (uptime & self-wake)

**Hard fact first:** software cannot boot a powered-off machine. Cron and systemd timers do not run
while the PC is off, so they cannot wake it. Only firmware/hardware can power on a dead machine. A
systemd timer *can* wake the host from **suspend** (via the RTC), but **not** from a full power-off.
This splits the problem into two states:

- **From OFF** → only BIOS/UEFI RTC alarm, Wake-on-LAN from another always-on device, or BIOS
  auto-power-on after AC loss can start it.
- **From SUSPEND** → a systemd timer with `WakeSystem=true`, or `rtcwake`, can resume it.

### Recommended pattern: suspend overnight, wake on schedule

Choose an AC inactivity timeout longer than the complete scheduled-job window. The systemd timers
installed in §1.5 include `WakeSystem=yes`, which sets the RTC alarm so the machine wakes from
suspend before each job fires. No cron daemon or always-on requirement is needed for the recommended
systemd path.

Example setup:

1. **AC inactivity timeout set to 60 minutes** — machine stays up through the full job window then
   auto-suspends:
   ```bash
   gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-timeout 3600
   ```
2. **Systemd timers with `WakeSystem=yes`** — installed via `local/install_trading_timers.sh`.
   Verify with `systemctl list-timers --all | grep -E 'daily-|weekly-'` (unit names carry no
   `trading-` prefix — see Part 1.5).
3. **AC Power Recovery in BIOS/UEFI** — set to **On** or **Last State** so a power blip brings
   the machine back. (Board-specific menu path — capture below.)

### Missed-run safety net (independent of wake reliability)

Even with the above, treat a missed run as expected-occasionally, not catastrophic:

- Backfill any gap with `replay_daily_runs` (see
  [runtime-operations.md](runtime-operations.md#run-did-not-execute-scheduler-missed)).
- The health-check job + alert webhook tell you when a run is missing so you can react.

### Record machine-specific details privately

Copy this checklist into `local/operations/production-host-checklist.md` and complete it there. Tracked
runbooks describe reusable procedures; they do not record the state of a particular installation.

- [ ] BIOS/UEFI vendor + version, and the exact menu path + label for **AC power recovery**
- [ ] Whether the board supports **RTC wake / Power On by Alarm**, and its menu path (or note "not supported")
- [ ] Confirmed `systemd WakeSystem=yes` wakes from suspend on this hardware
- [ ] NIC **Wake-on-LAN** capability (`ethtool <iface> | grep Wake-on`) and whether to enable it
- [ ] Distro + version noted; `systemd-logind` AC inactivity timeout recorded
- [ ] Uptime decision recorded: always-on or suspend+wake; AC power recovery configured

The private installation checklist should also record whether another host still has these jobs
registered. Unregister any superseded schedule before enabling this host so jobs cannot run twice.

---

## Part 6 — IB Gateway, the weekday awake window, and the health alert

For accounts on `interactive_brokers_socket_paper`. Nothing here is verified on a host yet. Each
assumption that decides whether it works is marked UNVERIFIED, and 6.6 is how to settle them.

The design: IB Gateway stays logged in
all week through IBKR's own auto-restart, so the host stays awake from Sunday evening until after
Friday's close, and you log in to the Gateway once, on Sunday night. Between Friday's close and Sunday
evening the host may suspend.

### 6.1 Install and configure IB Gateway

Install IB Gateway (the stable build) from IBKR's own installer on the host, as the user that runs the
jobs. Start it from the desktop session and log in with the IBKR **paper** login. IBKR does not support a
headless Gateway, so it needs the desktop session; the owner starts and logs in to it, and nothing in
this repo starts it.

In the Gateway's settings:

| Setting | Value |
|---|---|
| API > Enable ActiveX and Socket Clients | on |
| API > Read-Only API | off (orders are sent through it) |
| API > Socket port | `4002` (paper) |
| API > Trusted IPs | `127.0.0.1` only |
| Lock and Exit > Auto restart | on, at a time outside IBKR's own maintenance window |
| Lock and Exit > Never lock | on |

The Gateway's window can be minimised; do not quit it. IBKR allows one session per username, so a Client
Portal Gateway logged in with the same login may disconnect this one; stop it first.

### 6.2 The awake window

Three system units plus a stop service. A system unit is needed because only the system manager can set
the RTC alarm that wakes a suspended host. Replace `<user>`, `<repo>`, and `<env-file>` (an absolute path
to `.env`). All times are Pacific; the explicit time zone keeps them right if the host's zone changes.

`/etc/systemd/system/trading-awake.service`, which holds a sleep inhibitor for as long as it runs:

```ini
[Unit]
Description=Keep the host awake for the IBKR trading week

[Service]
ExecStart=/usr/bin/systemd-inhibit --what=sleep:idle:handle-lid-switch --who=trading --why="IBKR trading week" --mode=block /usr/bin/sleep infinity
```

`/etc/systemd/system/trading-awake-start.timer`, which wakes the host on Sunday and starts the window:

```ini
[Unit]
Description=Start the IBKR trading week awake window

[Timer]
OnCalendar=Sun *-*-* 18:00:00 America/Los_Angeles
WakeSystem=true
Persistent=true
Unit=trading-awake.service

[Install]
WantedBy=timers.target
```

`/etc/systemd/system/trading-awake-stop.timer` and its service, which end the window after the close
(Friday's 16:00 ET close is 13:00 PT; the half hour covers the post-trade reconcile):

```ini
[Unit]
Description=End the IBKR trading week awake window

[Timer]
OnCalendar=Fri *-*-* 13:30:00 America/Los_Angeles
Unit=trading-awake-stop.service

[Install]
WantedBy=timers.target
```

`/etc/systemd/system/trading-awake-stop.service`:

```ini
[Unit]
Description=Stop the IBKR trading week awake window

[Service]
Type=oneshot
ExecStart=/usr/bin/systemctl stop trading-awake.service
```

The Sunday time is when the host wakes, not when you must log in: log in before the health alert's
grace period ends (6.3). Choose the time you want.

`systemd-inhibit` holds a `sleep` block, which makes logind refuse a suspend request while it is held.
UNVERIFIED that the desktop's idle suspend and the lid switch respect it on this host; 6.6 checks it.
If they do not, mask the targets for the week instead (`systemctl mask sleep.target suspend.target
hibernate.target hybrid-sleep.target` from the start unit, `unmask` from the stop one).

### 6.3 The health alert

`/etc/systemd/system/ibkr-gateway-health.service`, which runs only while the awake window does:

```ini
[Unit]
Description=IB Gateway health alert
BindsTo=trading-awake.service
After=trading-awake.service

[Service]
User=<user>
WorkingDirectory=<repo>
EnvironmentFile=-<env-file>
ExecStart=<repo>/.venv/bin/python -m trading.interfaces.runtime.jobs.maintenance.ibkr_gateway_health --port 4002 --client-id 901
Restart=on-failure
RestartSec=30

[Install]
WantedBy=trading-awake.service
```

Install the units, enable the timers, and enable the health unit so the window starts it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now trading-awake-start.timer trading-awake-stop.timer
sudo systemctl enable ibkr-gateway-health.service
```

The worker connects to the API port every 300 seconds, reads the managed accounts, and alerts through
the webhook and SMTP settings in `.env` once a failure has lasted 900 seconds (`--grace-seconds`), so
the Gateway's nightly restart passes without an alert. A Gateway that is down or at its login screen on
Sunday evening alerts after that grace period: that is the reminder to log in. It sends one more alert
when the Gateway is back. Its options are in the [runtime jobs reference](../reference/runtime-jobs.md).

### 6.4 Client ids

IBKR allows one API connection per client id. Do not reuse these:

| Client id | Used by |
|---|---|
| each account row's `broker_client_id` (default `1`) | the daily run, and any operator tool that builds a broker for that account |
| `901` | the health alert |
| `99` | `scripts.ibkr_socket_smoke_test`, as in the paper-trading runbook |

Today every phase of the daily run connects and disconnects, so an operator tool can run between phases.
A job that holds a connection open (not built) would keep the account's id, and tools would need another.

### 6.5 Moving an account onto the socket venue

1. If the host still has the retired Client Portal units, remove them so they stop failing every 30
   seconds: `systemctl --user disable --now ibkr-keepalive.service ibkr-gateway.service`, then delete
   their unit files from `~/.config/systemd/user/`.
2. Log in to IB Gateway (6.1).
3. Point the account at the socket venue with `broker_type = 'interactive_brokers_socket_paper'`, its
   `broker_port` set to `4002`, and a `broker_client_id`; the SQL and the in-flight order caveat are in the
   [IBKR paper trading runbook](ibkr-paper-trading.md). Do this only when the account has no open orders.
4. Run `python -m scripts.ibkr_socket_smoke_test --port 4002 --client-id 99` before the first daily run.

### 6.6 First-week checks

These settle what is UNVERIFIED above. Record the answers in `local/operations/production-host-checklist.md`.

| Check | How | Settles |
|---|---|---|
| The inhibitor holds | Sunday after the window starts: `systemd-inhibit --list` shows `trading`; leave the host idle past the desktop's suspend timeout and confirm it stays up | the idle suspend and lid switch respect it |
| The host wakes | Suspend it before Sunday 18:00: `systemctl list-timers trading-awake-start.timer` shows the next run; it should be awake at that time | `WakeSystem` works on this hardware |
| Login survives the week | Log in Sunday; each morning check `journalctl -u ibkr-gateway-health.service -n 5` shows no alert and the daily run connected | the Gateway's auto-restart needs no login mid-week |
| Login after a weekend suspend | Sunday evening: is the Gateway still logged in, or at its login screen? | whether the Sunday login is a fresh one every week |
| A fill that lands while no job is connected, and fractional sizes | During market hours: `python -m scripts.ibkr_socket_smoke_test --port 4002 --client-id 99 --fill-lookup-check --fill-order-symbol <SYM> --fill-order-qty 0.5`. It fills a small paper order, reconnects, and prints what `get_order` rebuilds. Paper accounts only | `get_order` rebuilds the fill from executions and completed orders, and the socket accepts a fractional size |
| A fill that arrives in two parts | The same command prints each fill's price when the fill came in parts; compare them with IBKR's statement | each fill is priced at its own execution price |
