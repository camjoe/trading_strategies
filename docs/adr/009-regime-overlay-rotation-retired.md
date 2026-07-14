# ADR: Regime/overlay rotation retired (design preserved for future revival)

Type: adr
Status: Accepted
Created: 2026-07-07
Last Reviewed: 2026-07-07
Purpose: Record why the regime-driven account-rotation selection (policy regime + news/social overlays)
was removed when rotation was unified onto the decision-score contract, and preserve its design so it
can be revived if performance-based rotation is later augmented with regime awareness.
Related: the rotation-convergence work (completed; retrievable from git history)

## Context

The system had two rotation paradigms: **performance-based** (champion/challenger + the decision-score
contract; and the account `select_optimal_strategy` over a schedule) and **regime-driven**
(`select_regime_strategy`). The convergence unifies rotation onto the single decision-score contract.

A 2026-07-07 investigation of the live DB found the regime/overlay path **provably unused**: all
accounts had `rotation_overlay_mode='none'`, no `rotation_regime_strategy_*` values, and none in
`rotation_mode='regime'`; no account profile configured it. The regime branch was therefore
unreachable dead code. Rather than keep dead-but-untested code inline (which works against the goal of
reducing rotation sprawl), we remove it and preserve the design here for revival.

## Decision

Remove the regime/overlay **rotation selection** code (commit `74312df`, branch
`features/phase4-2b-unified-rotation`). Retrieve the exact implementation with
`git show 74312df` or `git log --follow -- src/trading/services/auto_trading/rotation.py`.

**What it did (for future revival):** when `rotation_mode == "regime"`,
`select_account_rotation_strategy` called `select_regime_strategy`, which:

1. Required a non-empty `rotation_schedule`; otherwise returned `None`.
2. Probed the **policy** feature provider (`SPY`) and classified a regime via `classify_policy_regime`
   from `POLICY_RISK_ON_SCORE` / `POLICY_DEFENSIVE_TILT` against the risk-on/risk-off thresholds →
   `risk_on` / `neutral` / `risk_off`.
3. If `rotation_overlay_mode` ∈ {`news`, `social`, `news_social`}, computed a **news/social overlay
   vote** across the account's covered tickers (holdings ∪ `rotation_overlay_watchlist`): each ticker
   voted +1/0/−1 from news sentiment and/or social trend; a confident net majority
   (`rotation_overlay_min_tickers`, `rotation_overlay_confidence_threshold`) nudged the regime one
   notch along `("risk_off", "neutral", "risk_on")`.
4. Mapped the final regime to the `rotation_regime_strategy_{risk_on|neutral|risk_off}` account column,
   returning it if present in the schedule (else the active strategy).

Removed symbols: `select_regime_strategy`, `classify_policy_regime`,
`select_rotation_overlay_direction`, `apply_rotation_overlay_to_regime`,
`_classify_news_overlay_vote`, `_classify_social_overlay_vote`, `fetch_rotation_overlay_tickers`
(services/auto_trading/rotation.py); the `mode == "regime"` branch in `select_account_rotation_strategy`
+ its runtime wrappers; and `resolve_rotation_regime_strategy` / `resolve_rotation_overlay_mode` /
`resolve_rotation_overlay_watchlist` (domain/rotation.py).

**Kept:** the `policy_regime` / `news_sentiment` / `social_trend` feature providers and their
alternative-strategy signal functions (`domain/strategy_signals.py`) — they are consumed by strategies,
not just rotation.

## Consequences

- **Account columns left in place.** `rotation_regime_strategy_*`, `rotation_overlay_mode`,
  `rotation_overlay_watchlist`, `rotation_overlay_min_tickers`, `rotation_overlay_confidence_threshold`
  remain on `accounts` (the migration system is append-only). They are inert; `rotation_mode='regime'`
  now behaves like the default performance-based path.
- **Revival path.** To bring regime rotation back on the unified book-keyed model: restore the removed
  functions (from git), and feed the regime output as a **candidate-enumeration** input to the
  champion/challenger decision (2b-2), rather than as a separate selection branch — this keeps the
  single decision-score selection path while adding regime awareness.
- **Config plumbing retired (2b-7, 2026-07-07).** The `RotationConfig` model, profile parser, web API
  contract, and frontend controls for `mode` / `optimality_mode` / `regime_strategy_*` / `overlay_*` were
  removed (no-ops once selection converged on champion/challenger). The `accounts` columns stay
  (append-only) and the `book_rotation_settings` mirror still carries them; the revival path above now
  also re-adds this config plumbing (recoverable from git). No persisted data is lost.
