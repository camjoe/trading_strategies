---
name: Python Statistical Modeling
layer: portable
description: Portable starter skill for building and evaluating Python statistical models for finance or other time-series domains.
use_when:
  - designing modeling pipelines
  - validating time-series evaluation methodology
  - comparing baseline and more advanced predictive models
localize_with:
  - modeling entrypoints and data modules
  - evaluation rules
  - validation commands
---

## Goal

Build statistically sound, reproducible modeling workflows with appropriate baselines, chronology-aware validation, and clear trade-offs.

## Responsibilities

1. Define the objective, target, horizon, and success metric.
2. Prepare data with explicit handling for missingness, leakage risk, and chronological splits.
3. Build interpretable baselines before more complex models.
4. Evaluate with diagnostics that fit the domain and the model's operational use.

## Constraints

1. Do not use random splits for temporally ordered data unless explicitly justified.
2. Do not ignore leakage, overfitting, or unstable baselines.
3. Do not hardcode domain constants inline when they belong in named constants.

## Localize for a project

Fill in:

- the relevant data and modeling modules
- the approved validation commands
- project-specific evaluation and reporting rules

## Expected output

1. Objective and assumptions
2. Modeling plan
3. Validation approach
4. Risks and next experiments
