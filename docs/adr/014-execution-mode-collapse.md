# ADR: Execution-Mode Collapse and Book-Owned Rotation Scheduling

Type: adr
Status: Accepted
Created: 2026-07-10
Last Reviewed: 2026-07-10
Purpose: Record the collapse of the account/book runtime split onto one book-keyed path and the move
of rotation scheduling ownership onto `book_rotation_settings`.
Related: [ADR 010](010-book-keyed-execution-model.md), [ADR 011](011-strategy-catalog-and-parameter-ownership.md)

## Context

After sleeve retirement the runtime still carried two execution paths selected by a job flag: the
book path (which production always ran — the daily DAG hard-coded `--execution-mode book`) and an
account-mode path that traded only the default book with an account-wide strategy, gated by an
interval-based rotation cadence (`is_rotation_due`, `rotation_last_at`, `rotation_active_index`).
Rotation inputs were split incoherently: the live book path read `accounts.rotation_schedule` and
`accounts.rotation_lookback_days` while ignoring the cadence machinery entirely, and
`book_rotation_settings` had scheduling columns nothing read.

## Decision

1. **One execution path.** `run_for_account` is the market-window gate plus the book run. Every
   active, openly assigned book trades — the default book included (`enumerate_trading_books` no
   longer excludes it). Unassigned books do not trade. The `execution_mode` flag, constants, and
   the account-mode trade loop are deleted.
2. **Rotation scheduling is book-owned.** `book_rotation_settings` supplies each book's
   `rotation_enabled` gate, challenger `rotation_schedule`, and evidence `rotation_lookback_days`,
   resolved per-field with code-default fallback (`resolve_book_rotation_schedule`; missing row =
   rotation disabled). The interval cadence dissolves: rotation is continuous champion/challenger
   evaluation gated by the per-book `cooldown_days` policy — what production already did.
3. **Rotation state is the assignment record.** `book_strategy_assignments`
   (`effective_from`/`effective_to`) and `rotation_decisions` (`decision_time`) carry
   strategy-at-time-T attribution; the account state columns (`rotation_active_*`,
   `rotation_last_at`) retire. The active strategy resolves from the default book's open
   assignment (`active_strategy_for_account`), and explicit strategy edits sync that assignment.
4. **Contracts are rewritten, not shimmed.** Profiles, the admin API, and the frontend carry a
   nested `rotation` object (`enabled`, `schedule`, `lookback_days`), applied to the default
   book's settings row. The CLI edits scheduling via `configure-book-rotation` (interface primacy).
5. **Columns retire append-only.** All 17 account `rotation_*` columns and the book interval
   columns stay on their tables but are no longer materialized, read, or written (the 2b-7
   precedent). Existing databases completed a one-time book-rotation cutover; its temporary
   data-op and runbook were then retired.

## Accepted behavior changes

- Former account-mode accounts submit at most one intent per book per run (`max_trades` becomes a
  cross-book cap) instead of a sequential multi-trade loop, and now write `risk_snapshots` /
  `risk_decisions` audit rows (an upgrade). Trade notes use the `book_fill` format.
- The interval cadence is gone; churn control is the per-book `cooldown_days` policy.
- The global trade throttle now gates the book submission loop (previously only the deleted
  account loop enforced it — production book mode ran unthrottled); a hit cap blocks further
  submissions and records a `trade_throttle_exceeded` risk decision.
- Books with rotation disabled (or no settings row) are skipped by rotation evaluation entirely —
  they no longer write daily hold-decision rows.
- An account with no book schedule loses the implicit `[account.strategy]` challenger fallback:
  an empty schedule means incumbent-only evaluation.

## Consequences

- The execution-mode collapse plan and one-time cutover tooling were retired after all environments
  completed the cutover.
- The rotation core (`evaluate_book_rotation`, cooldown, decision log) and the parameter policy-editing
  surface are unchanged.
- Future rotation features (per-book cadence preferences, schedule editing UI) extend
  `book_rotation_settings` — never the account row.
