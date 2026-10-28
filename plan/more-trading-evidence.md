# Plan: more trading and more evidence on the IBKR paper accounts

Status: drafted 2026-10-09; design B chosen 2026-10-19. Not started. Nothing below has been run against the IBKR host.
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
| Trade more than once per day | Decided 2026-10-19: design B, a periodic intraday job (not extra scheduled daily runs). Built as B1 below: the scheduler learns a repeat interval. |
| What an intraday run acts on | Decided 2026-10-19: partial-day bars. An intraday run evaluates strategies on today's unfinished bar. Whether the data provider returns one is UNVERIFIED and is step 1. |
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

### 3. Intraday runs (design B1, chosen 2026-10-19)
A new runtime job that runs every N minutes through US market hours, started by a scheduler that learns a
repeat interval. Rejected: design A (extra `daily_paper_trading` entries) because the duplicate-run guard
skips every run after the first `COMPLETE` of the day; design B3 (one job started each morning that loops until
the close) because it is a long-running process on a host that sleeps, with its own crash and restart handling,
where B1 keeps one short process per run, one log per run, and the existing timer model.

**Scheduler (verified in the code, 2026-10-19).** A schedule entry has one `time` (`HH:MM`) and an optional
`day_of_week`; `job_catalog.py` and `scheduler_installer.py` have no repeat interval. Add one, for example
`interval_minutes` with a window start and end, and teach the installer's three targets (systemd `OnCalendar`,
cron, Windows Task Scheduler) to express it. The production host is Linux, so systemd comes first.
UNVERIFIED: how the installer's cron and Windows paths would express a windowed interval; the host's timezone and
daylight-saving handling for a window in market time.

**The intraday job.**
- New runtime job (use the `create-runtime-job` skill) with its own job name and period tag, so the daily job's
  `COMPLETE` sentinel and duplicate-run guard are untouched, and the daily health check still watches only the
  daily log.
- Trading only: reconcile, trade, reconcile. The snapshot, the report, and the success notification stay with
  the daily job.
- Its run artifacts must not be named `daily_paper_trading_*.json`: burn-in and the daily report read that
  pattern, and several runs a day would be counted as one date's runs (a failure or broker anomaly in any run
  fails the date). Decide separately whether burn-in should ever count intraday runs.
- Alerts: a skipped-account, broker-anomaly, or unresolved-orders `warn` repeats on every run. Send an intraday
  alert once per day per account and cause, or only on a change.

**Reruns and duplicate orders (verified: selection code).** Buys are signaled tickers not already held and
sells are signaled tickers held, so once a fill is reconciled a rerun with the same signal does nothing, and
step 01 applies fills before each run trades. The gap is an order still working at the broker: the ticker is
not held yet, so a rerun could buy it again. The intraday job needs an explicit "skip a ticker that has an open
or pending order" check before it submits.

**Partial-day bars (the chosen input).** Strategies evaluated on an unfinished bar can flip between buy and
sell within a day. Risks to settle before shipping:
- Whipsaw and same-day round trips. Consider a minimum hold or hysteresis, and confirm whether a signal that
  flips back should be acted on at all.
- IBKR day-trading rules for small margin accounts: UNVERIFIED whether they apply to this paper account.
- What the data provider returns for today before the close (verified 2026-10-28, 14:06 Eastern, probe on the
  host, AAPL/MSFT/NVDA): yfinance returns a bar dated today at the `1d` interval, and a fresh fetch a couple of
  minutes later shows a different close and a higher volume for all three. Intraday runs can therefore see new
  data; the bar is unfinished, so signals must tolerate a partial day. Checked once, in one session.
- The market-data cache (verified in the code): signals read `fetch_ohlcv(ticker, period, "1d")`, which goes
  through a 24-hour on-disk cache keyed by ticker, period, and interval. A second run in the same day reads the
  first run's bars from disk, so intraday runs see no new data unless the cache is disabled
  (`TRADING_MARKET_DATA_CACHE_DISABLED`) or its lifetime is cut for the intraday job. This must change with the
  intraday job. The probe confirmed it: the cached bar equalled the first fetch while a fresh fetch differed for
  two of three tickers.
- Backtests and the evidence the advisor reads assume daily-bar decisions. Intraday trades are a different
  kind of evidence; label them so the scorecards and promotion review can separate them.

**Other consequences to settle (none verified yet).**
- One shared cash pool across seven accounts: more trades means more chances to run out of cash.
- Rate limits and session health on the IBKR gateway (the global 10 requests per second guard). The branch
  `feature/ib-gateway-socket-switch` replaces the Client Portal keepalive with a held IB Gateway connection and a
  gateway health check, and sets a weekday awake window; intraday runs must fit inside that window.
- Order of work with the contract-rules plan (`contract-trading-rules.md`): a bigger universe makes more
  contract types likely, which that plan exists to handle.

## Suggested order
1. Done: what the data provider returns for today's bar before the close (see the risks above). Intraday runs
   can produce new signals if they bypass the cache.
2. Run the daily job as is for a few weeks to build a baseline. Record trades per account per day.
3. Universe change on one account, then the rest.
4. Decide on caps from the logs.
5. Scheduler interval support (its own pull request), then the intraday job (another), then resolve the
   partial-bar risks above before enabling it on more than one account.

## Developer verification (fill in when the work ships)
- `list-accounts` / `parameters` show the new universe.
- Run logs show the new run times and the trades per run.
- The scheduler lists the intraday job with its interval and window; the daily job's schedule is unchanged.

## Out of scope
Renaming accounts. Enabling rotation. Changing strategy signal logic.
