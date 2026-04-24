## Test Support Notes

`tests/support/` is the shared helper layer for repeated test fixtures, fakes, seed data, and small harnesses.

Current guidance:

- Prefer adding new helpers to the most specific module possible, such as `backtesting.py`, `auto_trading.py`, or `admin.py`.
- Avoid treating `tests/support/__init__.py` as the default place to expose every helper.
- Prefer direct imports from the specific helper module when a helper is only used by one area or one test family.
- Keep `tests/support/__init__.py` for genuinely common convenience exports, not as a catch-all surface.

Why this matters:

- The individual helper modules are still reasonably well-scoped.
- The main risk of drift is `tests/support/__init__.py` becoming a broad utility dump that hides ownership and encourages unrelated coupling.
- If future cleanup is needed, review `__init__.py` first before splitting the area into more files.
