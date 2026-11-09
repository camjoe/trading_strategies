# Plan: make accounts and books trade differently

Status: drafted 2026-10-28. Not started. Nothing below has been run against the IBKR host.
Branch to use: `feature/distinct-books`, off `develop`.

## Goal
Today the seven IBKR paper accounts are clones, so their trades are largely the same evidence repeated.
Make books (and through them accounts) differ on purpose, so the history rotation, promotion review, and
the advisor read is broader. This plan covers the knobs that make books differ and the budget that limits
them. It does not cover more runs per day or a bigger universe in general; see `more-trading-evidence.md`.

## What exists (verified in the code, 2026-10-28)
- The auto-trader already trades by book. `generate_book_trade_intents`
  (`src/trading/services/execution/selection/book_intents.py`) loops over an account's active books. Each
  book resolves its own strategy, parameters, universe (`books.trade_symbols`), risk policy, instrument
  mode, trade size, max position, and stop/take-profit.
- `books.max_trades_per_run` (nullable) limits one book within what the account has left. NULL adds no
  limit.
- The run's `max_trades` (5 primary, 11 other, per-account overrides) is an **account** budget. Books claim
  it in an order from `order_capacity_claimants`, seeded by the run date (`snapshot_time[:10]`), so the order
  is the same for every run on a given day and a book late in the order can get nothing.
- The service can edit a book's universe: `apply_book_config` writes `trade_symbols` when
  `AccountConfig.trade_universes` is set, and `configure_book` edits one named book (strategy, settings,
  rotation).
- Universe history is recorded (`book_universe_history`) on every change.

## What is missing
1. Verified 2026-10-28: no CLI flag reached `trade_universes` or `max_trades_per_run`, and `configure-account`
   edited only the default book. Item 1 below adds them.
2. The IBKR accounts are provisioned as clones (same strategy per account, same 12-ticker universe, 10% size,
   20% max position, no risk policy). Nothing says why each differs.
3. The account budget is shared. With several books per account, or with intraday runs, the date seed gives
   the same claim order every run.

## Work items

### 1. CLI: edit a book's universe and per-run limit (small, unblocks the rest) — done on `feature/distinct-books`
- Add `--trade-universes` (names or tickers; whichever `resolve_trade_symbols` accepts) and
  `--max-trades-per-run` to the book edit path that reaches `configure_book`. Validate through the
  existing settings validation. No migration: both columns exist.
- Tests: the edit writes the book, records universe history, and a NULL limit can be restored.
- Docs: `docs/reference` command table; `README` of the CLI if it lists options.

### 2. Decide the differences (owner decision; tooling done)
Tooling: two public example universes (`defensive`, `cyclical`) and `docs/runbooks/differentiating-books.md`. Which accounts get what stays the owner's call, kept out of tracked files.
Candidates, from least to most invasive. Record the chosen ones in the PR, not here.
- **Different universes per account.** Slices of `growth.txt` plus `default.txt`, with overlap. Large caps
  move together, so more names add trades but less independent evidence than the count suggests; prefer
  names in different sectors (`symbol_sector_map` exists).
- **Different sizing per account:** trade size, max position, stop-loss and take-profit.
- **One account, several books.** The same account trades two or more books with different strategies or
  universes. Per-book `max_trades_per_run` then keeps one book from using the whole account budget.
- **Different strategies per account.** Already the case for the seven local accounts; the IBKR copies
  mirror them. Check what the IBKR copies actually assign before changing it.
- Open: do all accounts keep sharing one IBKR cash pool? More differing books means more claims on the same
  cash; see "Other consequences" in `more-trading-evidence.md`.

### 3. Fair budget sharing across books (only if item 2 puts several books in one account)
- Today: one account budget, a claim order fixed for the date.
- Options: (a) rely on per-book `max_trades_per_run` and leave the order alone; (b) seed the order from the
  run timestamp so each run rotates (matters mainly once intraday runs exist); (c) split the budget evenly
  by book first, then give the remainder to whoever still has signals. (a) needs no code.
- Decide only after item 2, and after checking logs for a book that was starved. UNVERIFIED that any book
  has been starved today.
- The risk gate consumes its own account caps "in intent order" (a comment in `book_intents.py`), so any
  change to the order has to be checked there too.

### 4. Label the evidence
Trades from differing books are only useful if the advisor and scorecards can tell them apart. Books are
already the unit the advisor decides on (`strategy-advisor`). Confirm that scorecards are keyed by book, not
account, before relying on this. UNVERIFIED.

## Constraints
- Respect layering (`docs/architecture/architecture-conventions.md`). The CLI change is interface-layer
  only; the service already exists.
- Strategy parameters and universes for the real accounts may be private. Only intentionally public examples
  go in tracked files; the real per-account choices belong under `local/strategies/` or in the database, not
  in this repository (`AGENTS.md`, core rules).
- Do not touch `live_trading_enabled`, `broker_type`, or the paper-account assertion.
- Backtests are unchanged.

## Suggested order
1. Item 1 (CLI options). Independent of everything else, and `more-trading-evidence.md` item 1 needs it.
2. Item 2 on `ibkr_momentum_5k` alone, as that plan suggests; look at its trades after a few weeks.
3. Item 3 only if several books share an account or intraday runs start.

## Developer verification (fill in when the work ships)
- `parameters` and `list-accounts` show the per-book universe and limit.
- A run log shows each book's trades, and a book with a limit stops at it.

## Out of scope
Intraday runs, caps for the daily job (see `more-trading-evidence.md`), enabling rotation, changing strategy
signal logic, renaming accounts.
