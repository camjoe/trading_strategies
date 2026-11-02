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
trades several books, the cap is shared across them one trade at a time: with a cap of 4 and two
books that both have signals, each gets 2, and a book with fewer signals leaves the rest to the other.
A book's `--max-trades-per-run` also keeps it from using more than that many trades:

```bash
python -m trading.interfaces.cli.main configure-account --account <account> --book <book> \
    --max-trades-per-run 2
```

A value above the account cap has no effect, and the limit cannot be cleared back to none from the CLI.

## Pick differences that add evidence

- Large companies move together. Two books holding different large caps are less independent than
  the ticker count suggests; prefer books that differ by sector or by strategy.
- Change one thing per book first (universe, or sizing), so a difference in results has one cause.
- Try it on one account and read its trades after a few weeks before changing the rest.
- Accounts that trade through one IBKR paper account draw on one cash pool. More differing books
  means more claims on that cash.
- A universe wider than large caps may include contracts that reject fractional sizes; see
  `plan/contract-trading-rules.md` before widening it a lot.

## Confirm

```bash
python -m trading.interfaces.cli.main parameters --account <account>
```

The next daily run's log lists each book's trades. A book with a limit stops at it.
