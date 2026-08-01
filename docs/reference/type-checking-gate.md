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

Dropping `--follow-imports=skip` is the fix, and it is its own piece of work: the
error volume is unknown, and pandas-typed surfaces will need either stubs
(`pandas-stubs`) or explicit `Any` annotations before the tree is clean. Do it as a
deliberate project with a measured starting error count, not as a flag flip inside
another change.
