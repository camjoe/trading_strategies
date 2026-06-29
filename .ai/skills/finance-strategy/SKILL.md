---
name: finance-strategy
description: Explains financial terminology, classifies strategies, interprets signals, and describes market mechanics in enough depth to guide implementation work. Use when asked about trading strategies, financial concepts, market mechanics, signal interpretation, or domain terminology.
invoker: any
---

# Finance and Strategy

Use this skill for domain explanation, not for personalized investing advice.

## Workflow

1. Define the relevant concepts precisely.
2. Classify the strategy or signal by edge source, horizon, and regime.
3. Explain implementation risks such as leakage, overfitting, execution costs, and corporate actions.
4. Map the concept to the appropriate code layer or module family when useful.

## Constraints

- Do not invent market data or performance outcomes.
- Do not give personalized investment advice.
- Do not treat concept explanation as a substitute for a full modeling pipeline.

## Repo references

- `src/trading/domain/`
- `src/trading/backtesting/`
- Domain notes under `docs/reference/`

## Expected output

1. Concept summary
2. Classification or mechanics explanation
3. Codebase alignment notes
4. Risks and caveats
