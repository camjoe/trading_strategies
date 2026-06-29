# Production Runtime Host Setup & Deployment Runbook

Type: runbook
Status: Draft
Created: 2026-06-27
Last Reviewed: 2026-06-27
Purpose: Step-by-step setup of the dedicated Linux runtime host and the ongoing test-and-deploy workflow that promotes code to it, with a trackable setup checklist.
Related: [Production Runtime Hosting ADR](../adr/007-production-runtime-hosting-and-deployment.md), [Runtime Operations Runbook](runtime-operations.md), [Runtime Jobs Reference](../reference/runtime-jobs.md), [Branching](../conventions/branching.md), [DB Migration System](../reference/db-migration-system.md)

This runbook implements [ADR 007](../adr/007-production-runtime-hosting-and-deployment.md): one dedicated
Linux host runs the scheduled jobs from a production checkout that tracks `main`, development happens
elsewhere, and every deploy passes a pre-deploy test gate. Read the ADR first for the *why* (including
why blue/green is deferred). This runbook is the *how*.

Conventions used below (adjust to your host):

| Placeholder | Meaning | Example |
|---|---|---|
| `<user>` | Login user on the Linux host | `cam` |
| `~/trading-prod` | Production checkout (tracks `main`, cron runs from here) | `/home/cam/trading-prod` |
| `~/trading-staging` | Optional staging checkout (tracks `develop`, no cron) | `/home/cam/trading-staging` |

Repo URL (already filled into the commands below): `https://github.com/camjoe/trading_strategies.git`

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
2. **Set the timezone** — cron fires on local time, so this must match the timezone your schedule
   times assume:
   ```bash
   timedatectl                       # check current
   sudo timedatectl set-timezone America/New_York   # set to your market timezone
   ```
3. **Disable sleep/suspend** so the host stays up unattended:
   ```bash
   sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
   ```
   On a laptop lid, also set `HandleLidSwitch=ignore` in `/etc/systemd/logind.conf`, then
   `sudo systemctl restart systemd-logind`.
4. **Ensure cron runs and starts on boot:**
   ```bash
   sudo systemctl enable --now cron
   ```
5. Configure unattended security updates to **not** auto-reboot during market hours (or schedule any
   reboot window outside them). This is the Linux analogue of the Windows-update problem we are
   leaving behind.

### 1.2 Production checkout + venv

```bash
git clone https://github.com/camjoe/trading_strategies.git ~/trading-prod
cd ~/trading-prod
git checkout main
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements-base.txt   # runtime-only deps (no test deps needed in prod)
```

### 1.3 Secrets and configuration

Copy the committed template and fill in real values:

```bash
cd ~/trading-prod
cp .env.example .env        # .env is gitignored
$EDITOR .env                # set TRADING_IBKR_WEB_API_ACCOUNT_ID, TRADING_RUNTIME_ALERT_WEBHOOK_URL, etc.
chmod 600 .env              # readable only by the runtime user
```

> **Secrets policy (deterministic).** Create the real `.env` **only on this production host**, never
> in a dev checkout where coding agents run. `.gitignore` stops a file from being *committed* — it does
> **not** stop an agent or tool from *reading* it. The protection that actually works is the secrets
> not existing on the machine where agents operate. Keep `.env` mode `600` owned by the runtime user,
> and do not run coding agents on this host. (Optional defense in depth on the dev machine: a Claude
> Code `permissions.deny` read rule for `**/.env` and secret paths.)

**Important — the runtime jobs do not auto-load `.env`.** Unlike the web backend (which loads
`apps/paper_trading_web/backend/.env` via dotenv), the cron job entrypoints read `os.environ`
directly. So you must get these vars into the job's environment one of two ways:

- **Source the file in a cron wrapper.** Point each cron command at a tiny wrapper script:
  ```bash
  # ~/trading-prod/run-job.sh
  #!/usr/bin/env bash
  set -euo pipefail
  cd "$(dirname "$0")"
  set -a && . ./.env && set +a
  exec ./.venv/bin/python "$@"
  ```
  ```bash
  chmod +x ~/trading-prod/run-job.sh
  ```
  Then register schedules with `--python /home/<user>/trading-prod/run-job.sh` in §1.5 so every
  job inherits the env. (The wrapper forwards `-m <module> …` straight through.)
- **Or** declare the vars directly in the crontab (export lines / `KEY=value` header) above the
  generated job lines.

At minimum set:
- `TRADING_RUNTIME_ALERT_WEBHOOK_URL` so missed/failed runs are visible (see
  [runtime-operations.md](runtime-operations.md#webhook-notifications)).
- `TRADING_IBKR_WEB_API_ACCOUNT_ID` (required) — configure the rest of the IBKR connection per
  [broker-setup-ibkr.md](../reference/broker-setup-ibkr.md).

### 1.4 Seed the database

- SQLite lives under `local/` (gitignored). Either copy the current paper-trading DB from the old
  host into the same relative path under `~/trading-prod/`, or initialize fresh and run migrations.
- Confirm migrations are current (see [db-migration-system.md](../reference/db-migration-system.md)).

### 1.5 Register the schedule (cron)

`manage_job_schedules` writes cron lines that `cd` into the checkout it is run from, so run it from
`~/trading-prod` and point `--python` at the production venv — or, if you used the env wrapper from
§1.3, at `~/trading-prod/run-job.sh` instead (so jobs inherit `.env`). **Always `--dry-run` first** and
read the lines it would write:

```bash
cd ~/trading-prod
./.venv/bin/python -m trading.interfaces.runtime.jobs.manage_job_schedules \
    --python /home/<user>/trading-prod/.venv/bin/python \
    --daily-paper-trading-time 13:10 \
    --daily-paper-trading-fallback-time 14:10 \
    --health-check-time 16:30 \
    --weekly-db-backup-time 02:00 --weekly-db-backup-day-of-week Sunday \
    --dry-run
```

Re-run without `--dry-run` to install. See the
[Runtime Jobs Reference](../reference/runtime-jobs.md#registering-schedules) for every available
entry (snapshot, backtest-refresh, challenger shadow-eval) and their flags. Verify:

```bash
crontab -l        # confirm the expected lines, each cd-ing into ~/trading-prod
```

### 1.6 Verify end to end

```bash
cd ~/trading-prod
# A safe manual run of the daily job (or --dry-run if you want zero writes):
./.venv/bin/python -m trading.interfaces.runtime.jobs.daily.paper_trading --force-run
# Confirm health check sees a fresh successful artifact:
./.venv/bin/python -m trading.interfaces.runtime.jobs.daily.trader_health
```

Then confirm monitoring per [runtime-operations.md](runtime-operations.md): logs land in `local/logs/`,
artifacts in `local/exports/`, and `python -m scripts.check_jobs` summarizes status.

---

## Part 2 — Ongoing deploy workflow

The rule from [ADR 007](../adr/007-production-runtime-hosting-and-deployment.md): **the scheduler only
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
.venv/bin/python -m scripts.run_checks --profile ci
# Targeted suites for the areas you touched (faster signal)
.venv/bin/python -m scripts.checks.run_suite --base develop
```

For a risky change, also smoke it in the **staging checkout** (Part 3) with `--dry-run` against a copy
of the production DB before promoting.

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
# If a DB migration shipped: apply it (see db-migration-system.md)
# If job set or schedule times changed: re-run Part 1.5 registration
```

### 2.5 Post-deploy verification

```bash
cd ~/trading-prod
./.venv/bin/python -m trading.interfaces.runtime.jobs.daily.trader_health
python -m scripts.check_jobs
```

Watch the next scheduled run complete (look for the `COMPLETE` sentinel per
[runtime-operations.md](runtime-operations.md)).

---

## Part 3 — Optional staging checkout (pre-deploy smoke test)

A lightweight stand-in for blue/green (see [ADR 007 §4](../adr/007-production-runtime-hosting-and-deployment.md#decision)).
It has **no cron**, so it never trades — it exists only for manual dry-runs.

```bash
git clone https://github.com/camjoe/trading_strategies.git ~/trading-staging
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
./.venv/bin/python -m scripts.run_checks --profile ci
./.venv/bin/python -m trading.interfaces.runtime.jobs.daily.paper_trading --dry-run
```

---

## Part 4 — Rollback

No hot standby (by design — ADR 007 §4). Rollback is a git checkout, plus DB restore only if data was
affected:

```bash
cd ~/trading-prod
git log --oneline -n 10            # find the last-good commit
git checkout <good-sha>            # detached HEAD on the known-good code
./.venv/bin/pip install -r requirements-base.txt   # if deps differ
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

### Recommended pattern: always-on + self-recover + scheduled-power-on safety net

This is the most reliable for unattended daily runs and needs the least moving parts:

1. **Disable sleep/suspend** (already in §1.1) so the host never drops into a state a missed wake
   could strand it during the trading day.
2. **Auto-recover from power loss.** In BIOS/UEFI set **"Restore on AC Power Loss" / "AC Power
   Recovery" → On (or Last State)**. A power blip then brings the machine back by itself.
3. **No login required to run jobs.** cron (and systemd services) run without an interactive login;
   confirm `systemctl enable --now cron` (§1.1) and that the runtime user's crontab is installed.
   Do not gate jobs behind a desktop session/auto-login.
4. **Scheduled power-on safety net (optional but recommended).** In BIOS/UEFI enable **"Power On by
   RTC Alarm" / "Wake on RTC"** to power the machine on daily a bit before market open. Then even a
   full shutdown self-corrects before the first job.

### Alternative: suspend overnight, wake on schedule (power saving)

Only if you care about idle power draw and accept an extra failure mode:

- Let the host suspend when idle, and schedule an RTC wake before the daily run. Either a systemd
  timer unit with `WakeSystem=true`, or an `rtcwake` call (e.g. `rtcwake -m no -t $(date +%s -d 'tomorrow 06:00')`
  to arm the next wake). Validate it actually wakes *before* relying on it — RTC-from-suspend support
  varies by board.

### Missed-run safety net (independent of wake reliability)

Even with the above, treat a missed run as expected-occasionally, not catastrophic:

- Register the **fallback** paper-trading entry (`--daily-paper-trading-fallback-time`, §1.5) — a
  second duplicate-guarded attempt later in the day.
- Backfill any gap with `replay_daily_runs` (see
  [runtime-operations.md](runtime-operations.md#run-did-not-execute-scheduler-missed)).
- The health-check job + alert webhook tell you when a run is missing so you can react.

### TODO — capture machine-specific details on the Linux host

The exact settings below are board/distro-specific and should be filled in **while on the Linux PC**.
Until then this section stays `Draft`.

- [ ] BIOS/UEFI vendor + version, and the exact menu path + label for **AC power recovery**
- [ ] Whether the board supports **RTC wake / Power On by Alarm**, and its menu path (or note "not supported")
- [ ] Confirm `rtcwake`/systemd `WakeSystem` behavior from suspend on this hardware (works / doesn't)
- [ ] NIC **Wake-on-LAN** capability (`ethtool <iface> | grep Wake-on`) and whether to enable it
- [ ] Distro + version, init/power-management specifics (`systemd-logind` lid/idle settings as configured)
- [ ] Decision recorded: **always-on** vs **suspend+wake**, and which power-on safety net is enabled

---

## Setup progress checklist

Tick these as the one-time setup is completed on the Linux host. (Mirrors ADR 007 follow-ups.)

- [ ] 1.1 Base system: packages installed, **timezone set**, sleep/suspend disabled, cron enabled,
      auto-reboot kept out of market hours
- [ ] 1.2 Production checkout `~/trading-prod` on `main` with its own `.venv` (requirements-base)
- [ ] 1.3 Secrets in `.env` on the host only (mode 600), loading mechanism chosen; no `.env` on dev machine
- [ ] 1.4 Database seeded and migrations current
- [ ] 1.5 Cron schedule registered from `~/trading-prod` with prod venv; `crontab -l` verified
- [ ] 1.6 End-to-end manual run + health check pass; monitoring confirmed
- [ ] Confirmed cron survives a reboot (reboot the host, verify next run fires)
- [ ] Part 5 uptime configured: AC-power-recovery on, sleep disabled, (optional) RTC power-on enabled
- [ ] Part 5 machine-specific details captured on the Linux host (fills in the TODO list)
- [ ] Decided whether to stand up the optional staging checkout (Part 3) now or later
- [ ] Old Windows host scheduled tasks unregistered so jobs don't double-run
      (`manage_job_schedules --unregister` on the old machine) — currently none registered (verified 2026-06-27)
