# Test Support

## Purpose

`tests/support/` is the shared helper layer for repeated test fixtures, fakes, seed data, and small harnesses.

The package is intentionally organized by test area rather than as one large utility module. Examples include:

- `tests.support.auto_trading`
- `tests.support.backtesting`
- `tests.support.cli_main`
- `tests.support.runtime_jobs`

## Usage

- Prefer adding new helpers to the most specific module possible, such as `backtesting.py`, `auto_trading.py`, or `admin.py`.
- Prefer direct imports from the specific helper module when a helper is only used by one area or one test family.
- Avoid treating `tests/support/__init__.py` as the default place to expose every helper.
- Keep `tests/support/__init__.py` minimal; it is a package marker and guidance point, not a broad convenience facade.

## Notes

- The individual helper modules are still reasonably well-scoped.
- The main risk of drift is `tests/support/__init__.py` becoming a broad utility dump that hides ownership and encourages unrelated coupling.
- When this area drifts, review `__init__.py` first before splitting it into more files.
