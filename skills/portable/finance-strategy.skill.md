---
name: Finance and Strategy
layer: portable
description: Portable starter skill for explaining financial terminology, classifying strategies, interpreting signals, and describing equity-market mechanics.
use_when:
  - explaining a financial concept
  - classifying a strategy or signal
  - mapping market mechanics to code or workflow design
localize_with:
  - domain modules
  - reference docs
  - architecture placement rules
---

## Goal

Explain trading and market concepts precisely enough that they can guide implementation and evaluation decisions in a codebase.

## Responsibilities

1. Define terms, signals, strategies, and market mechanics clearly.
2. Classify a strategy by edge source, holding period, and market regime.
3. Explain implementation risks such as leakage, overfitting, execution costs, or corporate-action effects.
4. Map the concept to the correct code layer or module family when relevant.

## Constraints

1. Do not make up market data, returns, or future outcomes.
2. Do not provide personalized investment advice.
3. Do not pretend concept explanation is the same as building a modeling pipeline.

## Localize for a project

Fill in:

- the relevant domain, backtesting, or services modules
- the repo's architecture placement rules
- any reference docs that act as canonical financial definitions

## Expected output

1. Concept summary
2. Classification or mechanics explanation
3. Codebase alignment notes
4. Risks and caveats
