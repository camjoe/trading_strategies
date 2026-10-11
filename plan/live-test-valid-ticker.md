# Plan: add is_valid_ticker (throwaway live test of the plan pickup)

Status: in progress (branch `feature/live-test-valid-ticker`). Before pickup: drafted 2026-10-11.
Throwaway plan for the live test of the plan pickup; delete it afterwards.

## Goal
Add one small pure helper, `is_valid_ticker`, to `src/common/tickers.py` so callers can check a symbol's
shape before using it. Nothing calls it yet; this plan exists to exercise the pickup, not the product.

## What to build
`is_valid_ticker(symbol: str) -> bool` in `src/common/tickers.py`.

A symbol is valid when it is, exactly as given (no stripping, no case change):
- one to five capital letters, `A` to `Z`, optionally followed by one `.` or `-` and then one or two
  capital letters. Examples that are valid: `AAPL`, `F`, `BRK.B`, `BF-B`, `RDS.AB`.
- Examples that are not valid: an empty string, `aapl`, `AAPLXX` (six letters), `BRK.`, `.B`, `BRK.BCD`,
  `A B`, `A1`, and any string with leading or trailing whitespace.

## Tests
Add a `TestIsValidTicker` class to `tests/src/common/test_tickers.py` that covers every example above.

## Docs
Add `is_valid_ticker` to the `tickers.py` row of `docs/maps/common-map.md`.

## Not in scope
Do not change any other function, add callers, or touch anything outside `src/common/tickers.py`, its test
file, and that one map row.

## Done when
- the new tests pass and the gate (`python -m scripts.run_checks pr`) passes against the base the
  controller names;
- the map row lists the new function.
