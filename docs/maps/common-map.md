# Common Map

Type: map
Status: Active
Created: 2026-06-24
Last Reviewed: 2026-06-24
Purpose: Inventory the `src/common/` shared kernel — small, dependency-light utilities imported across `src/trading`, `src/infrastructure`, `apps/`, and `scripts/`.
Related: [Trading Package Map](trading-package-map.md), [Infrastructure Map](infrastructure-map.md)

## Purpose

`src/common/` is the shared kernel: generic primitives with no dependency on the trading domain, safe to import from any package. Keep it lean — domain-specific logic belongs in `src/trading/`, not here.

## Module Directory

| Module | Responsibility |
|---|---|
| `coercion.py` | Defensive value/row coercion helpers (`coerce_float`, `row_expect_float/int/str`, `row_float`) |
| `constants.py` | Shared cross-module constants (annualization factor, basis-points divisor, settlement ticker, …) |
| `tickers.py` | Ticker-file parsing (`parse_ticker_tokens`, `load_tickers_from_file`, `load_ticker_categories`) |
| `time.py` | Timezone-aware time helpers (`utc_now_iso`, `parse_utc_iso`) |
| `runtime_job_status.py` | Shared runtime job-status types used by jobs and reporting |

### `src/common/paths/`

Path resolution helpers.

| Module | Responsibility |
|---|---|
| `repo_paths.py` | Repo-root discovery (`get_repo_root`) for path-relative resolution |
| `project_paths.py` | Project data paths (incl. frozen back-compat data locations) |

## Related References

- `docs/architecture/architecture-conventions.md` — constants placement and shared-kernel guidance
