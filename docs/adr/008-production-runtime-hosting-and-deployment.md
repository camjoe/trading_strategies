# ADR: Production Runtime Hosting and Deployment Strategy

Type: adr
Status: Accepted
Created: 2026-06-27
Last Reviewed: 2026-07-22
Purpose: Record where the scheduled runtime jobs run in production, how code is promoted to that host, and why full blue/green is deliberately deferred for the paper-trading phase.
Related: [Production Runtime Host Runbook](../runbooks/production-runtime-host.md), [Runtime Operations Runbook](../runbooks/runtime-operations.md), [Runtime Jobs Reference](../reference/runtime-jobs.md), [Branching](../conventions/branching.md), [DB Migration System](../reference/db-migration-system.md)

## Context

The scheduled runtime jobs (daily paper-trading DAG, daily snapshot/health/backtest-refresh,
weekly/monthly governance, weekly DB backup) must run reliably and unattended. Running them from the
same workstation used for development produced two recurring failure modes:

1. **Code churn breaks running jobs.** The jobs execute out of the same git checkout that is actively
   edited, so in-progress work is picked up by the scheduler mid-change.
2. **Host unreliability.** A workstation used as a server may be turned off, sleep, or reboot during a
   scheduled window, so runs silently do not fire.

Relevant facts that constrain the solution:

- Jobs are **short-lived processes** fired by the OS scheduler (cron on Linux, Task Scheduler on
  Windows) via `python -m <module>` — there is no long-running daemon to keep alive. See
  [scheduler_installer.py](../../src/trading/interfaces/runtime/scheduling/scheduler_installer.py).
- [manage_job_schedules.py](../../src/trading/interfaces/runtime/scheduling/manage_job_schedules.py)
  registers cron lines that `cd` into the checkout it is run from and accepts `--python`, so a
  separate production checkout + venv produces a self-contained schedule with no extra tooling.
- Persistence is **SQLite** — a single file, single-writer. This is the dominant constraint: two
  concurrent job loops cannot safely share one database, and giving them separate databases makes a
  "test against production" environment meaningless.
- The repo already uses a **main / develop** branch model where `main` is "stable, production-ready,
  PR-only" ([branching.md](../conventions/branching.md)). A production release gate already exists.
- Current scheduled operation is **paper trading only**. A missed or late run does not place live
  capital at risk.

Alternatives considered for the host:

- **Keep scheduling on the development workstation.** Rejected — development churn, sleep, and reboot
  behavior make it an unreliable runtime host.
- **Cloud VPS (Hetzner / Lightsail / DigitalOcean, ~$5/mo).** Viable and strictly more reliable
  (pro power/network, trivial off-site backups). Deferred, not rejected: it is the planned upgrade
  for the live-money phase. For paper trading it adds monthly cost and setup effort for reliability
  that exceeds current need.
- **Dedicated Linux host.** Chosen — it separates development from operation and uses the cron path
  already supported in code without requiring additional orchestration.

## Decision

1. **Single dedicated production host.** A Linux host is the recommended always-on production runtime
   environment. Cron is the scheduler (already supported); the host is configured not to sleep and to
   run on a fixed, correct timezone so schedule times align with market hours.

2. **Production runs from a dedicated checkout + venv, never the dev working copy.** A separate clone
   (e.g. `~/trading-prod`) with its own `.venv` holds the running code. Development edits never reach
   the scheduler until promoted. This is the direct fix for failure mode #1 and is independent of the
   host choice.

3. **`main` is the production ref; promotion is the deploy.** The production checkout tracks `main`.
   Deploying = merge `develop` → `main` via PR (existing gate), then `git pull` on the host. No new
   branch concept is introduced. Every deploy passes the pre-deploy test gate in the runbook before
   the pull lands.

4. **No full blue/green during the paper-trading phase.** Two concurrently *running* production
   environments are rejected because the SQLite single-writer model makes them either unsafe (shared
   DB → double trades / corruption) or pointless (separate DBs → divergent state that does not
   represent production). Instead:
   - One production environment runs the schedule.
   - An **on-demand staging checkout** (e.g. `~/trading-staging`, tracking `develop`, **no cron**,
     run manually with `--dry-run` against a *copy* of the production DB) is the pre-deploy smoke
     test. It never trades because nothing schedules it.
   - Rollback is `git checkout <previous-good-sha>` in the production checkout plus, if data was
     affected, DB restore from the weekly backup — not an environment swap.

5. **Revisit blue/green at the live-money transition.** When real capital and zero-downtime cutover
   or instant rollback become requirements, re-open this decision alongside the VPS move. That is the
   point where the cost of a true standby environment is justified.

6. **Secrets live only on the production host, never in a dev checkout.** The repo carries only
   `.env.example`; the real secrets file exists solely on the Linux host (mode `600`, owned by the
   runtime user) and is loaded into the cron environment (jobs read `os.environ` directly — they do
   not auto-load `.env`). Rationale: `.gitignore` prevents *committing* a file but does **not** prevent
   a tool or coding agent with filesystem read access from reading it. The deterministic protection is
   therefore physical: secrets are absent from the machine where coding agents run (the dev box), and
   no coding agent runs on the production host. Harness-level read-deny rules (e.g. Claude Code
   `permissions.deny` on `**/.env`) are optional defense in depth, not the primary control.

7. **Uptime is "always-on + self-recover," not software-scheduled wake.** The host stays powered with
   sleep disabled and BIOS AC-power-recovery on; an optional BIOS RTC power-on is the safety net.
   A powered-off machine cannot be woken by cron/systemd (only firmware/hardware can), so reliability
   rests on the host staying up plus the existing missed-run catch-up (fallback task + `replay_daily_runs`)
   rather than on a wake-from-off mechanism. Machine-specific BIOS/NIC details are captured on the host;
   see the runbook's Part 5 TODO.

## Consequences

Benefits:

- Failure mode #1 (code churn) is eliminated by construction: the scheduler can only see promoted
  `main` code in a checkout no one edits.
- Failure mode #2 (host unreliability) is removed by moving off the Windows desktop to an always-on
  Linux host with sleep disabled and cron persistence across reboot.
- Uses existing code paths (`manage_job_schedules` cron registration) and the existing `main`/`develop`
  gate — minimal new machinery.
- The staging-checkout approach gives most of blue/green's pre-deploy safety at near-zero cost.

Trade-offs / constraints imposed:

- The home Linux PC remains a single point of failure for power and internet. Accepted for paper
  trading; the VPS upgrade (Decision §5) addresses it for live money.
- Promotion to `main` now carries operational weight — it is a deploy. The pre-deploy test gate in
  the runbook is mandatory, not optional.
- Two checkouts (prod + optional staging) must be kept in sync on dependencies and migrations; the
  runbook's deploy steps cover `pip install` and schema migration on pull.
- No instant rollback to a hot standby — rollback is a git checkout + optional DB restore, which has
  a short window of downtime. Acceptable at paper-trading stakes.

Follow-ups:

- [ ] Execute the one-time host setup in
  [production-runtime-host.md](../runbooks/production-runtime-host.md) and tick its setup checklist.
- [ ] Confirm cron persists across a reboot and timezone is correct on the host.
- [ ] Decide whether to stand up the optional staging checkout now or add it at first risky deploy.
- [ ] Re-open this ADR (host + blue/green) when moving to live trading; pair with the VPS evaluation.
