# Plan: more trading and more evidence on the IBKR paper accounts

Status: drafted 2026-10-09. Not started. Nothing below has been run against the IBKR host.
Branch to use: `feature/more-trading-evidence`, off `develop`.

## Goal
Collect more paper-trading evidence faster. Today each IBKR account makes a few trades a day from one
run at one time. Rotation, promotion review, and the advisor all need trade history, and the rotation
gates need at least 20 trades in the lookback window (default 30 days) before they can act.

## Context
- Seven IBKR web-paper accounts (`ibkr_*`) mirror the seven local accounts: same strategies, same
  universe, 10% trade size, 20% max position, no risk policy. All seven share one IBKR paper account,
  so they draw on one real cash pool.
- Rotation is off everywhere and has no settings row. It stays off. It is a later step, once there is
  history. Account renaming is out of scope.
- The daily job `daily_paper_trading` runs once per weekday at the time in `job_schedule.json`. It
  submits orders only in US regular hours. It was set up recently, so there is little history yet.

## Decisions so far
| Decision | Status |
|---|---|
| Consider expanding the universe | Wanted. Size and which tickers undecided. |
| Consider raising the per-run trade caps | Possibly. Decide after the universe change shows whether caps bind. |
| Leave strategy signals as they are | Decided. Signals are likely fine. |
| Trade more than once per day | Wanted. Either extra scheduled runs or a periodic check through the day. Undecided which. |
| Address the consequences of intraday trading | Required as part of this work. See the list below. |

## Work items

### 1. Universe
- Known: `src/infrastructure/config/trade_universes/` has `default.txt` (12 tickers) and `growth.txt`
  (25 tickers). The daily job takes its universe from `books.trade_symbols`. Universe names are a
  write-time shorthand only (`docs/reference/runtime-jobs.md`).
- Known: all fourteen accounts hold the same 12 tickers today.
- UNVERIFIED: how to change `trade_symbols` on an existing book. `configure-account` has no flag for
  it, and `create-account` has none either. Read the book configuration service
  (`src/trading/services/books/configuration.py`) and the settings handlers before assuming a command
  exists; the answer may be a new CLI option.
- Open: which tickers, and whether every account gets the same list. Large caps move together, so more
  of them adds trades but less independent evidence than the count suggests.
- Suggested first step: try it on `ibkr_momentum_5k` alone.

### 2. Trade caps
- Known: `--primary-max-trades` defaults to 5 and `--other-max-trades` to 11 in
  `src/trading/interfaces/runtime/jobs/daily/paper_trading/arguments.py`. Per-account overrides exist in
  `caps.py`. A global `max_trades_per_day` throttle also exists (`configure-throttle`), unset by default.
- Known: these are ceilings, not targets. Signals produce the trades.
- UNVERIFIED: which accounts count as "primary", and whether the caps have ever bound. Check recent
  run logs for runs that stopped at the cap before changing any number.

### 3. More runs per day
Two designs, to be chosen:
- **A. More scheduled runs.** Add entries to `job_schedule.json`. UNVERIFIED: whether the scheduler
  accepts the same job id twice, and whether the entry would need distinct names.
- **B. A periodic check through the day.** A new or reworked job that runs every N minutes in market
  hours. Larger change; needs its own runtime-job scaffold (`create-runtime-job` skill).

Consequences to settle before shipping either design (none verified yet):
- The daily job also snapshots accounts, writes the report, and sends notifications on every run.
  Repeats would multiply those or need splitting from the trading step.
- Strategies use daily bars. More runs per day may mostly re-evaluate the same signal. Confirm that a
  second run in the same day does not re-submit an order for a signal already acted on.
- Open orders, partial fills, and reconcile timing between runs on the shared IBKR account.
- One shared cash pool across seven accounts: more trades means more chances to run out of cash.
- Rate limits and session health on the IBKR gateway (global 10 requests per second guard; the
  keepalive service).
- IBKR day-trading rules for small margin accounts: UNVERIFIED whether they apply to this paper
  account. Check before relying on same-day round trips.
- The success sentinel and the health check assume one daily run. Both need review.
- Order of work with the contract-rules plan (`contract-trading-rules.md`): a bigger universe makes
  more contract types likely, which that plan exists to handle.

## Suggested order
1. Run as is for a few weeks to build a baseline. Record trades per account per day.
2. Universe change on one account, then the rest.
3. Decide on caps from the logs.
4. Pick A or B for more runs and resolve the consequences list.

## Developer verification (fill in when the work ships)
- `list-accounts` / `parameters` show the new universe.
- Run logs show the new run times and the trades per run.

## Out of scope
Renaming accounts. Enabling rotation. Changing strategy signal logic.
