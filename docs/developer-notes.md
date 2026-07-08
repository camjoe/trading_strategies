# Developer Notes

Type: notes
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-07-08
Purpose: Durable developer gotchas only. What is left to build lives in [status.md](status.md);
standing pre-change checks live in `AGENTS.md` (venv interpreter, run the matching suite, read the
architecture conventions before touching `src/trading/`).
Related: [Status](status.md), [Decisions](decisions.md), [Overview](overview.md)

## Durable gotchas

- **CRLF warnings on commit are harmless** — the repo enforces line endings; `git` prints
  "CRLF will be replaced by LF" on commit. Not an error.
- **Paper results before 2026-07-03 are not strategy evidence** — until P1 landed, the trade path
  used a random placeholder, not strategy signals. Do not read pre-P1 paper history as evidence.
- **`mypy` must run via the project runner** — `python -m scripts.checks.python.mypy_check`
  (ad-hoc `mypy <file>` fails to resolve the `src/` layout and reports false import errors).
- **Backtest strategy labels are canonical keys** — `backtest_runs`/`walk_forward_groups` key
  `strategy_id`; reports show the catalog `strategy_key` (e.g. `trend`), not aliases
  (`trend_v1`). See [D14](decisions.md#d14).
- **Strategy knobs are still code defaults at runtime** — the `strategies` catalog stores
  `params_json`, but `resolve_strategy_params` returns registry `default_params` until the P6
  loader is wired (deferred — see [status.md](status.md)).
