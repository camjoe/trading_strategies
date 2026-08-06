# Common Map

Type: map
Status: Active
Created: 2026-06-24
Last Reviewed: 2026-07-25
Purpose: Inventory the `src/common/` shared kernel — small, dependency-light utilities imported across `src/trading`, `src/infrastructure`, `apps/`, and `scripts/`.
Related: [Trading Package Map](trading-package-map.md), [Infrastructure Map](infrastructure-map.md)

## Purpose

`src/common/` is the shared kernel: generic primitives with no dependency on the trading domain, safe to import from any package. Keep it lean — domain-specific logic belongs in `src/trading/`, not here.

## Module Directory

| Module | Responsibility |
|---|---|
| `coercion.py` | Defensive value/row coercion helpers (`coerce_float`, `row_expect_float/int/str`, `row_float`) |
| `constants.py` | Shared cross-module constants (annualization factor, basis-points divisor, settlement ticker, …) |
| `files.py` | Generic file metadata helpers (`modified_at_utc`, `modified_at_iso`, `sorted_by_mtime_desc`, `latest_by_mtime`) |
| `rate_limit.py` | Thread-safe outbound-call pacing and cumulative-call limiting (`RateLimiter`, `RateLimitExceeded`) |
| `revision.py` | Best-effort Git HEAD revision discovery for provenance and audit records (`git_head_revision`) |
| `tickers.py` | Ticker-file parsing (`parse_ticker_tokens`, `load_tickers_from_file`, `load_ticker_categories`) |
| `time.py` | Timezone-aware time helpers (`utc_now_iso`, `parse_utc_iso`) |
| `runtime_job_status.py` | Runtime job completion sentinels and run/step status vocabulary, imported directly by runtime jobs and the web backend |

### `src/common/paths/`

Path resolution helpers.

| Module | Responsibility |
|---|---|
| `executables.py` | Repo-local executable resolution helpers (`resolve_repo_python_exe`) |
| `formatting.py` | Cross-platform path display formatting helpers (`relative_posix`) |
| `repo_paths.py` | Repo-root discovery (`get_repo_root`) for path-relative resolution |
| `project_paths.py` | Project data paths (incl. frozen back-compat data locations) |

## Related References

- `docs/architecture/architecture-conventions.md` — constants placement and shared-kernel guidance
- `docs/conventions/python-style.md` — when to use common file/path portability helpers
