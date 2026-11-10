# Plan: make accounts and books trade differently

Status (2026-11-09): items 1, 3 and 4 and item 2's tooling are merged to `develop` (#332-#335), verified on
the dev PC sandbox (see Developer verification). Item 5 is built on `feature/broker-cash-check`. Nothing
has been run against the IBKR host.

Keep this file until the "Left to do" list is empty.

## Left to do
Check these off in the pull request that does each one; delete this file when none remain.
1. **Item 5, broker cash check.** Built on `feature/broker-cash-check`, not yet run on the host. Check the
   `TotalCashValue` the IBKR Web API returns against the Client Portal before relying on it (below).
2. **Item 2, the choice.** Pick each account's universe and sizing with `docs/runbooks/differentiating-books.md`
   and record it in the pull request or under `local/strategies/`, not in tracked files.
3. **Run it on the host.** Apply the choice to `ibkr_momentum_5k` first, then confirm in a run log that each
   book stops at its share, counting orders by `book_id` (the run log gives only the account total).
4. **Item 1 gap.** `configure-account --book` cannot set a book's `max_trades_per_run` back to NULL, and
   `create-account` does not take `--max-trades-per-run` or `--trade-universes`.
5. **Book cash.** No command sets a book's cash or divides an account's cash among its books; a book simply
   starts with the same amount as the others. The broker cash check needs one when the books drift from the
   broker (readiness note 3 on #338). Decide how books are funded, then add the command and point the
   runbook at it.
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

### 5. Check book cash against the broker (built on `feature/broker-cash-check`, 2026-11-09)
Each book spends from its own ledger cash, and accounts that reach one IBKR account share its real cash
balance, so the books together can promise more cash than the broker holds. In the daily run's pre-trade
step, after the reconcile has posted outstanding fills, `check_broker_cash`
(`daily/paper_trading/broker_preflight.py`) reads the broker's `TotalCashValue` through `get_account_info`
once per cash pool (every Web API account; socket accounts by host and port), adds up every book's cash across
the pool's accounts, and when the books hold more (beyond a $1.00 tolerance) skips each run account in the
pool for the day with a `warn` alert and the existing catch-up command. When that leaves no account to trade
the run fails with `BrokerCashShortfallError`. A broker answer with no usable cash figure skips the pool with
the reason (owner's decision, 2026-11-09: a warn, not a failed run) (the Web adapter now raises on a ledger with no `cashbalance` or `settledcash` instead of
returning 0.0). Simulator accounts are not checked. Operator text: `docs/runbooks/ibkr-paper-trading.md`
("Books hold more cash than the broker") and the tables in `docs/runbooks/ibkr-operations.md`.

Not verified: what the IBKR Web API ledger returns as `cashbalance` on the real paper account. Check one real
run's log line (`the books hold X cash and the broker holds Y`) against the Client Portal before relying on it.
Decided 2026-11-10 (owner): the pool is named from the four IBKR broker types in `domain/broker_cash.py`, and a
socket account with an unset host and port is a different pool from one naming the defaults (accepted, no real
account uses the socket transport); every account in a pool counts, run or not, and a stopped account's books
must be emptied or the account deleted (accounts have no inactive status to filter on).

Not covered: open orders that have reserved cash at the broker but are not yet filled, positions
(`get_positions` still has no caller), broker-side charges the books do not record (they build up past the
tolerance and need a manual reconcile), and two accounts that reach one IBKR account through different
settings (counted as two pools).

## Out of scope
Intraday runs, caps for the daily job (see `more-trading-evidence.md`), enabling rotation, changing strategy
signal logic, renaming accounts.
