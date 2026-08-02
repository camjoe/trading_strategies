# Type-Checking Gate — what mypy here does and does not catch

Type: notes
Status: Active
Created: 2026-08-01
Last Reviewed: 2026-08-02
Purpose: What the repo's mypy step verifies now that it follows imports, and what it still cannot catch.
Related: [Python Style](../conventions/python-style.md), [Architecture Conventions](../architecture/architecture-conventions.md)

## Purpose

Read this before relying on a type annotation to prevent a mistake.

## The invocation

`scripts/checks/python/mypy_check.py` runs:

```sh
mypy apps/paper_trading_web/backend src --python-version 3.14 --ignore-missing-imports
```

with `mypy_path` and `explicit_package_bases` set under `[tool.mypy]` in `pyproject.toml` —
without those, mypy cannot map a file path to a module name and stops before checking
anything.

**Cross-module types are checked.** Until 2026-08-02 the run also passed
`--follow-imports=skip`, which meant a module imported by the module under check was never
analysed and every symbol it exported resolved to `Any`. That flag is gone.

## What is caught

Type errors inside a module, and — now — anything depending on a type imported from another
module. The case that motivated the change:

```python
# registry.py — this now fails the gate
def _typed_wrong(history: int, params: dict, feature_history: None = None) -> str:
    return "hold"

STRATEGY_REGISTRY = {"trend": StrategySpec(signal_fn=_typed_wrong, ...)}
```

```
error: Argument "signal_fn" to "StrategySpec" has incompatible type
"Callable[[int, dict[Any, Any], None], str]"; expected
"Callable[[IndicatorView, Mapping[str, Any], Any | None], str]"
```

Verified by planting exactly that error against the real gate, not inferred from the flags.
This matters most for the contracts the codebase leans on structurally — `SignalFunction`,
`IbkrSocketClient`, `BrokerConnection`, `MarketDataProvider` — which were previously
documentation of intent and are now enforced.

## What is still not caught

`--ignore-missing-imports` remains, so third-party packages without stubs (pandas, yfinance,
`ib_async`) still resolve to `Any`. A call into one of those is unchecked, and so is anything
whose type comes back out of one. This is the remaining hole; closing it means stubs, not a
flag.

Runtime behaviour is also still out of scope. A green run says the annotations are
consistent, not that the code is right.

## Cost

Following imports is roughly 3x slower — about 21s to 62s cold on the full tree, measured
2026-08-02. Incremental runs are much cheaper. `--follow-imports-skip` restores the old
behaviour for a fast local pass, but a run under that flag is not evidence: every
cross-module type is `Any` again.

## What the transition cost

89 errors across 22 files when the flag first came off. They were not 89 separate bugs —
two root causes accounted for two thirds:

| Count | Pattern | Resolution |
|---|---|---|
| 51 | `sqlite3.Row` passed where `Mapping[str, object]` was expected | The backtesting repositories now convert with `dict(row)` at the boundary, matching the `from_mapping(dict(row))` pattern the other repositories already used |
| 16 | `JobContext.conn` typed `DBConnection \| None` | `DBConnection` is `sqlite3.Connection` rather than `Any`, and `JobContext.db` states the "this job opened a session" invariant once |
| 22 | assorted | Mostly annotations that had drifted from what the function returned, plus two narrow `Protocol`s where a concrete class had been named |

One real bug surfaced: `backtest_runs.warnings` is a `" | "`-joined TEXT column, and
`report_service` assigned it straight to a `list[str]` field, so anything iterating
`BacktestFullReport.summary.warnings` walked characters instead of entries. It had been
invisible because the row was untyped.

The lesson worth keeping: an annotation that no tool checks drifts from the code, and the
drift is silent. Two of the fixes above were annotations that had been wrong long enough to
be load-bearing in review.
