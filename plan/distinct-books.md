# Plan: make accounts and books trade differently

Status (2026-11-09): items 1, 3 and 4 are built, and item 2's tooling, as a stack of four pull requests,
all reviewed, with passing checks as of #332-#334; item 5 is decided but not built. Verified on the dev PC
sandbox (see Developer verification); nothing has been run against the IBKR host.

Pull requests, merged in this order with merge commits (not squash), each retargeted to `develop` after
the one below it merges:
1. #332 `feature/distinct-books` — item 1, the CLI.
2. #333 `feature/distinct-books-universes` — item 2's tooling: example universes and the runbook.
3. #334 `feature/distinct-books-budget` — item 3, the even share of the cap.
4. #335 `feature/distinct-books-evidence` — item 4, evidence labelling, and this file's progress notes.

Keep this file until the "Left to do" list is empty.

## Left to do
Check these off in the pull request that does each one; delete this file when none remain.
0. **Merge the four pull requests** in the order above, after bringing each up to date with `develop`.
1. **Item 5, broker cash check.** Decided, not built (below). Start it on its own branch off `develop`.
2. **Item 2, the choice.** Pick each account's universe and sizing with `docs/runbooks/differentiating-books.md`
   and record it in the pull request or under `local/strategies/`, not in tracked files.
3. **Run it on the host.** Apply the choice to `ibkr_momentum_5k` first, then confirm in a run log that each
   book stops at its share, counting orders by `book_id` (the run log gives only the account total).
4. **Item 1 gap.** `configure-account --book` cannot set a book's `max_trades_per_run` back to NULL, and
   `create-account` does not take `--max-trades-per-run` or `--trade-universes`.
5. **Stale doc.** The table row in `docs/reference/backtest-live-divergence.md` still says
   `max_trades_per_run` is never read; it is read in `book_intents.py`.
6. **Known limits, not planned.** An unused share is lost (item 3). Positions in tickers a universe switch
   drops are not managed by selection (runbook, "Check open positions first"). Promotion review has no
   per-book path (item 4).

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

### 3. Fair budget sharing across books (done: each book gets an even share of the cap)
- Each book gets `cap // books` trades, and the first `cap % books` books in claim order get one more. The
  claim order is seeded by run date. A book's own `max_trades_per_run` only lowers its share, and an unused
  share is not passed on. Stop-loss and take-profit exits are not counted against a share.
- Intents keep claim order, which the risk gate relies on when it consumes its own account caps.

### 4. Label the evidence (done)
The advisor is book-keyed. The account-level evaluation reports not isolated when an account has several books. Intraday labels wait for the intraday job.
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
- The run log gives only the account's trade total; per-book counts come from the `orders` table by
  `book_id` (query in `docs/runbooks/differentiating-books.md`). A book with a limit stops at it.
- Checked on the dev PC sandbox 2026-11-09 (account with three books, cap 6, `trend` on all): default 2,
  growth 2, limited book 1; no book above its share of 2. Not checked: exits past a stop-loss, a cap not
  divisible by the book count, the IBKR host.

### 5. Check book cash against the broker (decided 2026-11-02, not started)
Decision (owner): on a shortfall, raise an alert and skip that day's orders for the account. Do not shrink
the buys and do not trade through. Still to design: where the check sits relative to the broker preflight
and the order submission, which alert fires, what the sentinel and operator runbook say, and what a skipped
day looks like to the freshness and health checks. Read the broker figure first and record what it returns;
this touches the broker path, so review it in Aggressive mode and against the Live Trading Safety Guard.

Background. Each book spends from its own ledger cash, but nothing compares the books' balances with the broker. The
only equity check (`reconcile_book_equity`) compares the books with the account's own snapshot, and
`BrokerConnection.get_account_info` (cash, buying power) and `get_positions` have no production caller.
With several books on accounts that share one IBKR paper account, the ledgers can promise more cash than
the broker holds; an order then fails and the account's run stops (`broker_api_anomaly`). Decide whether to
read broker cash before submitting and what to do on a shortfall. UNVERIFIED: what `get_account_info`
returns on the IBKR web adapter.

## Out of scope
Intraday runs, caps for the daily job (see `more-trading-evidence.md`), enabling rotation, changing strategy
signal logic, renaming accounts.
