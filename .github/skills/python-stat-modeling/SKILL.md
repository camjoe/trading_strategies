---
name: python-stat-modeling
description: Builds or evaluates chronology-aware statistical modeling workflows for finance or other time-series domains. Use when asked about backtesting, alpha research, feature engineering, time-series modeling, leakage concerns, or evaluation methodology.
---

# Python Statistical Modeling

Use this skill for research, modeling, or methodology questions where time ordering matters.

## Workflow

1. Define the objective, target, horizon, and success metric.
2. Prepare data with explicit handling for missingness, leakage, and chronological splits.
3. Build interpretable baselines before more complex models.
4. Evaluate with diagnostics that match the domain and operational use.

## Constraints

- Do not use random splits for temporally ordered data without explicit justification.
- Do not ignore leakage, overfitting, or unstable baselines.
- Do not hardcode domain constants where named constants belong.

## Repo references

- `trading/backtesting/`
- `trading/services/analysis/`
- `docs/reference/notes-backtesting.md`

## Expected output

1. Objective and assumptions
2. Modeling plan
3. Validation approach
4. Risks and next experiments
