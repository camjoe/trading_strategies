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
| `json_columns.py` | The one wire format for JSON stored in a database column — `dumps_json_column` writes it, `row_json_object` reads it back |
| `constants.py` | Shared cross-module constants (annualization factor, basis-points divisor, settlement ticker, …) |
| `files.py` | Generic file metadata helpers (`modified_at_utc`, `modified_at_iso`, `sorted_by_mtime_desc`, `latest_by_mtime`) |
| `git.py` | Best-effort git interrogation of the checkout — arbitrary commands (`run_git`), repo-root discovery (`get_repo_root`), and HEAD revision for provenance (`git_head_revision`) |
| `paths.py` | Repo-relative path constants (`REPO_ROOT`, `LOCAL_DIR`, `LOGS_DIR`, …) and path display formatting (`relative_posix`) |
| `rate_limit.py` | Thread-safe outbound-call pacing and cumulative-call limiting (`RateLimiter`, `RateLimitExceeded`) |
| `tickers.py` | Ticker-file parsing (`parse_ticker_tokens`, `load_tickers_from_file`, `load_ticker_categories`) |
| `time.py` | Timezone-aware time helpers (`utc_now_iso`, `parse_utc_iso`) |
| `runtime_job_status.py` | Runtime job completion sentinels and run/step status vocabulary, imported directly by runtime jobs and the web backend |

## Related References

- `docs/architecture/architecture-conventions.md` — constants placement and shared-kernel guidance
- `docs/conventions/python-style.md` — when to use common file/path portability helpers
