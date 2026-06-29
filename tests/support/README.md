# Test Support

## Purpose

`tests/support/` is the shared helper layer for repeated test fixtures, fakes, seed data, and small harnesses used across multiple test suites. It is intentionally organized by test area rather than as one large utility module.

For the full per-file inventory, see the **Test Support Layout** section in [`tests/README.md`](../README.md#test-support-layout). Highlights:

- `seed/` — session-scoped DB population. `seed/db.py` is the orchestrator called by `tests/conftest.py`; the named constants it defines (`ACCT_TREND`, `ACCT_MOMENTUM`, `SLEEVE_TREND`, `SNAPSHOT_T1`, …) are the shared vocabulary for `seeded_conn` tests — reference them instead of hard-coding string literals.
- `account_records.py`, `accounts.py`, `analysis.py`, `backtesting.py`, `brokers.py`, `evaluation.py`, `promotion.py`, `reporting.py`, `repositories.py`, `sleeves.py` — per-area factory/insert helpers that return **real production types** (dataclasses, domain models), not `SimpleNamespace`.

Helpers used by only one suite live co-located with that suite rather than here (e.g. `tests/src/trading/services/auto_trading/factories.py`). Convention: if a co-located `factories.py` is imported from outside its own directory, move it to `tests/support/` under a domain-based name.

## Usage

- Prefer adding new helpers to the most specific module possible.
- Prefer direct imports from the specific helper module when a helper is only used by one area.
- Use real production types in helpers — not `SimpleNamespace` — unless the type comes from an external boundary that is impractical to construct.
- Avoid treating `tests/support/__init__.py` as the default place to expose every helper.

## Notes

- The main drift risk is `tests/support/__init__.py` becoming a broad utility dump that hides ownership and encourages unrelated coupling. When this area drifts, review `__init__.py` first before splitting into more files.
