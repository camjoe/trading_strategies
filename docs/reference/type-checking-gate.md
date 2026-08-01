# Type-Checking Gate — what mypy here does and does not catch

Type: notes
Status: Active
Created: 2026-08-01
Last Reviewed: 2026-08-01
Purpose: What the repo's mypy step actually verifies — intra-module errors only — so a cross-module annotation is not mistaken for an enforced constraint.
Related: [Python Style](../conventions/python-style.md), [Architecture Conventions](../architecture/architecture-conventions.md)

## Purpose

Read this before relying on a type annotation to prevent a mistake.

## The invocation

`scripts/checks/python/mypy_check.py` runs:

```sh
mypy apps/paper_trading_web/backend src --python-version 3.14 --ignore-missing-imports --follow-imports=skip
```

Two flags decide what gets checked:

- `--follow-imports=skip` — a module imported by the module under check is **not**
  analysed. Every symbol it exports resolves to `Any`.
- `--ignore-missing-imports` — third-party packages without stubs (pandas, yfinance,
  ib_async) also resolve to `Any`.

## What this means in practice

**Caught:** type errors contained within a single module.

```python
def _local() -> int:
    return "not an int"        # error: Incompatible return value type
```

**Not caught:** anything that depends on a type imported from another module.
`StrategySpec` is defined in `contracts.py`; in `registry.py` it is `Any`, so its
field types constrain nothing:

```python
# registry.py — accepted by the gate, though SignalFunction takes an IndicatorView
def _typed_wrong(history: int, params: dict, feature_history: None = None) -> str:
    return "hold"

STRATEGY_REGISTRY = {"trend": StrategySpec(signal_fn=_typed_wrong, ...)}
```

Both cases above were run against the real gate to confirm this, not inferred from
the flags.

## Consequence for readers and reviewers

Cross-module annotations in this repo are **documentation of intent**, not checked
constraints. They are still worth keeping accurate — they are what a reader and a
code review rely on — but a green mypy step is not evidence that a call site
matches the signature it targets. Where a cross-module contract genuinely must
hold, a test is the only thing that enforces it.

## Changing this

Dropping `--follow-imports=skip` is the fix. It is its own piece of work: **90
errors across 23 files**, measured 2026-08-01.

To reproduce, mypy also needs the `src/` layout spelled out — without it, it cannot
map a file path to a module name and stops before checking anything:

```sh
python -m mypy apps/paper_trading_web/backend src \
  --python-version 3.14 --ignore-missing-imports \
  --explicit-package-bases
```

with `mypy_path = "src:apps/paper_trading_web/backend"` and
`explicit_package_bases = true` under `[tool.mypy]` in `pyproject.toml`.

> Set `mypy_path` in the config file, not via the `MYPYPATH` environment variable.
> mypy splits that variable on `os.pathsep` — `;` on Windows — so a
> colon-separated value is read as one nonexistent directory, intra-repo modules
> silently fall back to `Any`, and the run reports far fewer errors than exist. A
> measurement taken that way reported 1 error when the real count was 90. Confirm
> any measurement by planting a deliberate cross-module type error and checking it
> is caught.

Two root causes account for most of it:

| Count | Pattern |
|---|---|
| 51 | `sqlite3.Row` passed where `Mapping[str, object]` is expected — `Row` is mapping-like at runtime but does not satisfy the protocol in typeshed |
| 16 | `Any \| None` passed where `Connection` is expected — connection helpers are not annotated tightly enough |
| 23 | assorted tail |

The two dominant patterns are systemic rather than 67 separate bugs, so the work is
tractable — but it is a project with its own branch, not a flag flip inside another
change. The concentration is also why the count is worth re-measuring before
starting: fixing either root cause moves it a lot.
