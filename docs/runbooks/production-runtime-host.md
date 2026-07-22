# Production Runtime Host Setup & Deployment Runbook

Type: runbook
Status: Draft
Created: 2026-06-27
Last Reviewed: 2026-07-22
Purpose: Step-by-step setup of the recommended dedicated Linux runtime host and the ongoing test-and-deploy workflow that promotes code to it.
Related: [Production Runtime Hosting ADR](../adr/008-production-runtime-hosting-and-deployment.md), [Runtime Operations Runbook](runtime-operations.md), [Runtime Jobs Reference](../reference/runtime-jobs.md), [Branching](../conventions/branching.md), [DB Migration System](../reference/db-migration-system.md)

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
    --env-file /home/<user>/trading-prod/.env \
    --daily-paper-trading-time <PRIMARY_HH:MM> \
    ...
```

Replace schedule placeholders with private operator values from
`local/operations/production-host-checklist.md`.

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
    --scheduler cron \
    --daily-paper-trading-time <PRIMARY_HH:MM> \
    ...
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

`manage_job_schedules` auto-detects systemd on Linux and generates systemd timer + service units with `WakeSystem=yes`, so the machine wakes from sleep before each job fires. It writes a sudo-ready install script to `local/install_trading_timers.sh`. Run from `~/trading-prod`. **Always `--dry-run` first:**

```bash
cd ~/trading-prod
python -m trading.interfaces.runtime.scheduling.manage_job_schedules \
    --daily-paper-trading-time <PRIMARY_HH:MM> \
    --daily-paper-trading-fallback-time <FALLBACK_HH:MM> \
    --health-check-time <HEALTH_HH:MM> \
    --weekly-db-backup-time <BACKUP_HH:MM> --weekly-db-backup-day-of-week <DAY> \
    --dry-run
```

Re-run without `--dry-run` to generate the install script, then apply it:

```bash
python -m trading.interfaces.runtime.scheduling.manage_job_schedules \
    --daily-paper-trading-time <PRIMARY_HH:MM> \
    --daily-paper-trading-fallback-time <FALLBACK_HH:MM> \
    --health-check-time <HEALTH_HH:MM> \
    --weekly-db-backup-time <BACKUP_HH:MM> --weekly-db-backup-day-of-week <DAY>

sudo bash ~/trading-prod/local/install_trading_timers.sh
```

See the [Runtime Jobs Reference](../reference/runtime-jobs.md#registering-schedules) for every available entry (snapshot, backtest-refresh, challenger shadow-eval) and their flags. Verify timers are active:

```bash
systemctl list-timers --all | grep trading
```

### 1.6 Verify end to end

```bash
cd ~/trading-prod
# Confirm the runtime can import, read its environment, and inspect recent artifacts:
python -m trading.interfaces.runtime.jobs.daily.trader_health
python -m trading.interfaces.runtime.jobs.maintenance.burn_in_status --force-run
```

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
# If job set or schedule times changed: re-run Part 1.5 registration
```

### 2.5 Post-deploy verification

```bash
cd ~/trading-prod
python -m trading.interfaces.runtime.jobs.daily.trader_health
python -m scripts.check_jobs
```

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
   Verify with `systemctl list-timers --all | grep trading`.
3. **AC Power Recovery in BIOS/UEFI** — set to **On** or **Last State** so a power blip brings
   the machine back. (Board-specific menu path — capture below.)

### Missed-run safety net (independent of wake reliability)

Even with the above, treat a missed run as expected-occasionally, not catastrophic:

- Register the **fallback** paper-trading entry (`--daily-paper-trading-fallback-time`, §1.5) — a
  second duplicate-guarded attempt later in the day.
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
