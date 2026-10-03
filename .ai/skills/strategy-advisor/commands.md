# Strategy Advisor — Repo Commands

The commands behind each step of the session procedure in `SKILL.md`. Prefix each with
`python -m trading.interfaces.cli.main` (from the repo `.venv`).

## Read and score

| Step | Command |
|---|---|
| Close the loop | `advisor-score` (optionally `--account <name>`) |
| Read the digest | `advisor-digest` (optionally `--account <name>`) |
| Account report | `report --account <name>` |
| Compare strategies' evaluations | `compare-strategies` |
| Promotion readiness | `promotion-status --account <name> [--strategy <key>]` |

## Evidence for a candidate

| Need | Command |
|---|---|
| A walk-forward experiment and its promotion gate | `backtest-optimize-show <experiment_id>` (prints `Promotion gate: PASS` or `FAIL (...)` and the trial audit) |
| A new sweep (one per hypothesis; needs approval — it takes minutes) | `backtest-optimize --account <name> --strategy <key> --search-space '<json>' --lookback-months 24` |
| Behavior and crash tails versus the incumbent | `backtest-bench --strategies <candidate>,<incumbent> --scenarios sharp_crash,melt_up_then_crash,choppy_flat` (catalog variant keys run with their own knobs) |
| The same on real history (needs captured fixtures) | `backtest-bench --strategies <candidate>,<incumbent> --scenarios covid_crash_2020_bootstrap,bear_2022_bootstrap` |

Paper results before 2026-07-03 are not strategy evidence (`docs/reference/backtesting.md`).

## Record a decision (every decision, immediately)

```sh
advisor-record --account <name> [--book <book>] --type <decision_type> \
    --strategy <kept_or_new_key> --alternative <rejected_key> \
    --decided-by agent:strategy-advisor/v2 \
    --rationale "<why, in one or two sentences>" \
    --note experiment=<id> --note gate=<PASS|FAIL> --note bench="<cells you read>"
```

`decision_type` is one of `hold`, `adjust_params`, `propose_variant`, `request_promotion`,
`disable_strategy`, `run_experiment`. Omit `--alternative` for `disable_strategy` and
`run_experiment`; `--strategy` defaults to the book's assigned strategy.

## Carry out an approved change (one approval per change)

| Change | Command |
|---|---|
| Switch a book's strategy | `assign-strategy --account <name> [--book <book>] --strategy <key>` (rejects unknown or disabled keys) |
| Promote a gated experiment winner | `backtest-optimize-promote <experiment_id> --key <new_key>` (never `--allow-no-edge`) |
| Create a tuned variant | `create-strategy-variant --strategy <new_key> --primitive <primitive> --set <knob>=<value>` |
| Disable a strategy | `configure-strategy --strategy <key> --enabled false` |
| Set a book's rotation challengers | `configure-book-rotation --account <name> [--book <book>] --schedule <key1>,<key2>` |
