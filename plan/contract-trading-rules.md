# Plan: per-contract trading rules (order increment and fractional eligibility)

Status: drafted 2026-10-09. Not started. The IBKR rules endpoint has NOT been checked on the host.
Branch to use: `feature/contract-trading-rules`, off `develop`, after #294 merges.

## Depends on
- PR #293 (merged 2026-10-09): `FRACTIONAL_SHARE_STEP = 0.0001`, `STORAGE_SHARE_STEP`,
  `closing_quantity_step_for`, decimal truncation in `sizing.py`, and SMART routing for fractional
  sizes in the web adapter.
- PR #294 `fix/ibkr-reconcile-order-status` (open): `BrokerConnection.get_order` and the reconcile
  lookup. The adapter changes overlap; do not start before it is in `develop`.

## Goal
Size every equity order to what IBKR accepts for that specific contract, instead of one assumed
increment. The owner will trade outside large-cap US stocks, where the assumption will fail.

## Evidence so far
Two real rejections on the IBKR paper account (2026-10-09), both from fractional MSFT orders:
1. `The size 0.934317 does not conform to the minimum variation of 0.0001 for this contract`
2. `Only IBKR SmartRouting supports fractional shares`

Both were fixed with constants: a global `0.0001` step, and `listingExchange: "SMART"` for any
fractional size. Only MSFT (then XOM, AMZN, which filled) has been tried.

## The assumptions this plan removes
| Assumption in the code today | Where | Risk |
|---|---|---|
| Every contract takes fractional sizes | `quantity_step_for` returns `FRACTIONAL_SHARE_STEP` for every equity book | A contract that is not fractional-eligible rejects every order for it, and one rejection stops the account's whole run (`broker_api_anomaly`). |
| Every fractional contract's increment is `0.0001` | `FRACTIONAL_SHARE_STEP` | The error text says the minimum variation is "for this contract". Another contract may differ. |
| The same step applies to every symbol in a book | `step_by_book` in the pre-submit gate | A book can hold symbols with different steps. |

## What is known vs unknown about IBKR
Known (from a web search of IBKR's documentation titles and snippets, not read in full; the doc pages
returned 403 to the fetch tool): the Client Portal endpoint `POST /iserver/contract/rules` returns
fields named `fraqInt` ("decimal places for fractional order size"), `cashQtyIncr` ("cash quantity
increment rules"), and `displaySize` ("standard display increment rule for the instrument").

UNVERIFIED, check on the host before designing around them:
- Exact request body (`conid`, `isBuy`, others) and whether one call per conid is enough.
- What `fraqInt` looks like for: a fractional-eligible stock (MSFT), a stock that is not eligible, an
  ETF, an ADR, a stock under $1, and a non-US listing. Is it absent, 0, or an integer for a
  non-eligible contract?
- Whether `fraqInt = 4` means the step is `0.0001` (10 to the power of minus `fraqInt`).
- Pacing and cost of the call (it needs a session; the client has a global 10 requests per second guard).

Host check (read-only; the account number is not printed by these calls). Needs the gateway logged in:
```bash
curl -sk -X POST https://localhost:5000/v1/api/iserver/contract/rules -H 'Content-Type: application/json' -d '{"conid": 272093, "isBuy": true}'
```
(272093 is MSFT, from the run log.) Repeat with the conid for each symbol class above. Look up conids
with `GET /iserver/secdef/search?symbol=<SYM>&secType=STK`. Paste the replies into the PR description.
Stop and revise this plan if the replies do not contain a usable increment or eligibility field.

## Design (to confirm after the host check)
A port, owned by the layer that needs it, implemented by the adapter:

- `TradingRules` (frozen dataclass, in `trading/models/`): `quantity_step: float`, the smallest order
  size increment, whole shares = `1.0`; fractional-ineligible contracts report `1.0`.
- `BrokerConnection.get_trading_rules(symbol) -> TradingRules | None`: non-abstract, default `None`
  (the broker cannot say). The paper adapter and the socket adapter keep the default.
- Web adapter: resolve the conid (existing `resolve_contract`), call the rules endpoint, map the field
  to a step. Cache per conid for the life of the connection (a run touches a handful of symbols).
  Any failure to read rules returns `None`.
- Sizing: when a symbol's rules are `None`, fall back to the conservative step, not the fractional
  one. Conservative = `WHOLE_SHARE_STEP`. A failed lookup then costs a smaller trade, never a rejected
  order that stops the run. (Decide this explicitly; it is the safety property of the change.)
- Per-symbol step travels on the intent (`BookTradeIntent.quantity_step`, new field) so the risk gate
  rescales each intent to its own step, replacing the per-book `step_by_book`.

Why not round in the adapter at send time: the order row is written before the send with the intended
size, and the risk gate has already approved that size. Rounding later makes the row, the gate, and
the broker disagree.

## Where the plumbing is (names, not line numbers; lines move)
- `trading/domain/auto_trading/sizing.py`: `quantity_step_for`, `choose_buy_qty`,
  `allocate_buy_quantities`, `closing_quantity_step_for`.
- `trading/services/execution/selection/selection.py`: `_size_buy_for_ticker` and the second sizing
  call (both pass `quantity_step_for(instrument_mode)`), and the closing-sell generator.
- `trading/services/execution/pre_submit_gate.py`: `step_by_book` and the `quantity_step=` it sets on
  the candidate; `trading/domain/risk_gate.py`: rescale rounds down to `intent.quantity_step`.
- `trading/models/execution.py`: `BookTradeCandidate.quantity_step`, `BookTradeIntent`.
- `trading/services/auto_trading/runtime.py`, `_run_books_for_account`: **the broker is created
  AFTER intents are generated and gated** (`broker = broker_factory(account)` comes after
  `gate.evaluate`). Sizing therefore has no broker today. Either open the broker before
  `generate_book_trade_intents` (restructure the early returns so it always disconnects), or build a
  small rules provider from the factory and pass it in. Note the daily run's step 00 already connects
  every account once (`check_broker_sessions`).
- `infrastructure/brokers/ibkr_web/adapter.py` and `client.py`: new rules call; `resolve_contract`
  already caches contract details.

## Constraints
- Respect layering (`docs/architecture/architecture-conventions.md`): the port lives in `domain`/`models`,
  the IBKR call in `infrastructure/brokers`, wiring in the service/runtime layer. `models` imports nothing.
- Do not touch `live_trading_enabled`, `broker_type`, or the paper-account assertion. Do not catch the
  three guard errors.
- Backtests keep whole-share sizing and must be unchanged.
- No new database column or migration. Rules are read from the broker per run and not stored.
- Comments state facts, not history (`docs/conventions/python-style.md`).

## Steps
1. Host check above. Record the replies. Revise this plan if the fields differ.
2. `TradingRules` model and the `BrokerConnection.get_trading_rules` default; tests for the default.
3. Web adapter implementation with a cache; adapter tests built from the recorded replies, including
   non-eligible and failed lookups.
4. Thread the rules into sizing and the gate: per-symbol step on the intent; remove the per-book step.
5. Conservative fallback when rules are unavailable; test that a failed lookup sizes whole shares.
6. Remove the global `FRACTIONAL_SHARE_STEP` assumption from the live path, or keep it only as the
   documented default for brokers that return `None`. Decide and say which.
7. Docs: `docs/reference/broker-integration.md`, `docs/reference/strategies.md` if sizing is described,
   and the `docs/reference/db-schema.md` note added by #293 about the order grid.
8. `python -m scripts.run_checks pr --base develop`, then `pr ready` (the independent reviewers and the
   readiness comment).

## Acceptance
- A fractional-eligible contract sizes on its own increment; a contract that is not eligible sizes whole
  shares; both verified with recorded IBKR replies as fixtures.
- A rules-lookup failure never raises out of sizing and never produces a fractional order.
- A mixed book (two symbols with different steps) rescales each intent to its own step.
- Backtest results are unchanged.
- On the host: a manual run for a paper IBKR account with a mixed universe places orders with no
  size or routing rejection.

## Risks and open questions
- If the endpoint does not distinguish eligibility, fall back to trying the order and learning from
  the rejection. That means a rejected order stops that account's run (`broker_api_anomaly`); decide
  whether a size rejection should skip the one symbol instead of halting the account. Separate change.
- Cost: one extra request per new symbol per run. Check the pacing table before adding a loop.
- Prices under $1 and non-US listings may have price tick rules that matter once limit orders are used;
  today every order is a market order, so no price is sent.
- Fills for fractional lots may arrive in sizes other than the order's; the reconcile lookup posts the
  cumulative size and does not depend on the increment.

## Hand-off prompt (for a fresh agent)
Read `AGENTS.md`, `docs/architecture/architecture-conventions.md`, and this file in full. Work on
`feature/contract-trading-rules` off `develop`. Do step 1 only if the owner supplies the replies; do not
guess IBKR fields. Follow the steps in order, run `python -m scripts.run_checks quick` after each, and
stop and report if a step's assumption fails.
