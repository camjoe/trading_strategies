# Differentiating Books

Type: runbook
Status: Active
Created: 2026-11-02
Last Reviewed: 2026-11-02
Purpose: Give accounts and books different universes, trade limits, and sizing so the paper-trading history is not the same evidence repeated.
Related: [Strategies Reference](../reference/strategies.md), [Runtime Operations](runtime-operations.md), [IBKR Paper Trading](ibkr-paper-trading.md)

Accounts created from one profile start identical: same strategy, same tickers, same sizing. Their
trades then repeat each other, which adds volume but little evidence. This runbook changes what a book
trades without touching code. Real assignments are private: keep them in the database, never in a
tracked file.

## Before you change anything

```bash
python -m trading.interfaces.cli.main list-accounts
python -m trading.interfaces.cli.main parameters --account <account>
```

`parameters` shows a book's tickers, trade size, max position, and per-run limit. Note the current
values so you can restore them. A universe can be restored only if the old tickers equal a named
universe file that has not changed; `--trade-universes` takes names, not tickers.

## Change a book's universe

Named universes are files under `src/infrastructure/config/trade_universes/`. Naming one stores its
tickers on the book at the moment you run the command; later edits to the file change nothing for that
book. The tracked examples are `default`, `growth`, `defensive`, and `cyclical`.

```bash
python -m trading.interfaces.cli.main configure-account --account <account> [--book <book>] \
    --trade-universes defensive
```

Several names are joined: `--trade-universes default,growth`. Without `--book` the account's default
book is edited. A name may contain only letters, digits, `_` and `-`.

**Check open positions first.** The switch replaces the book's tickers outright. The daily run prices
only the tickers the books carry, and a book sells or exits only tickers in its own list. A position
in a ticker the book no longer carries is not priced and gets no signal sell, stop-loss, or
take-profit exit until a book carrying that ticker is in the run. Close such positions, or keep the
ticker in the new list, before you switch.

## Change sizing or a risk policy

```bash
python -m trading.interfaces.cli.main configure-account --account <account> [--book <book>] \
    --trade-size-pct 5 --max-position-pct 15 --risk-policy stop_and_target \
    --stop-loss-pct 8 --take-profit-pct 20
```

## Limit one book's share of the account budget

The account has a per-run trade cap, set by the daily job's `--primary-max-trades` and
`--other-max-trades` arguments (and per-account overrides). When an account
trades several books, each book gets an even share of it: with a cap of 4 and two books, each may make
2 trades. A book that uses less than its share does not pass the rest on, so a slot can go unused. The
odd trade of an odd cap rotates by day, so a cap of 3 gives 2 and 1 one day and 1 and 2 the next. When
the cap is smaller than the number of books, only the first books in that day's order get a share.
Stop-loss and take-profit exits are not counted against a share and always go out.
A book's `--max-trades-per-run` lowers its share further:

```bash
python -m trading.interfaces.cli.main configure-account --account <account> --book <book> \
    --max-trades-per-run 2
```

A value above the book's share has no effect, and the limit cannot be cleared back to none from the CLI.

## Pick differences that add evidence

- Large companies move together. Two books holding different large caps are less independent than
  the ticker count suggests; prefer books that differ by sector or by strategy.
- Change one thing per book first (universe, or sizing), so a difference in results has one cause.
- Try it on one account and read its trades after a few weeks before changing the rest.
- Each book spends only its own cash balance. At the broker, accounts that trade through one IBKR
  paper account share one real cash pool, and nothing compares the books' balances with it, so the
  books' balances together should not exceed what the broker holds.
- A universe wider than large caps may include contracts that reject fractional sizes; see
  `plan/contract-trading-rules.md` before widening it a lot.

## Reading the evidence

The advisor digest reviews every book on its own: its strategy, its paper return since that strategy
was assigned, and its decisions. The evaluation artifact and promotion review read the account's
snapshots, which sum all of its books. When more than one book of an account has held equity (a book
that has since stopped trading still counts), that paper evidence is marked not isolated, and the
live-readiness check of promotion review lists it as a blocker instead of treating the account's return
as one strategy's. There is no per-book promotion path yet; judge each book from the digest.

## Confirm

```bash
python -m trading.interfaces.cli.main parameters --account <account>
```

The next daily run's log lists each book's trades. A book with a limit stops at it.
