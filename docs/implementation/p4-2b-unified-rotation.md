# Implementation Guide — P4 / 2b: Unified rotation/selection

Type: implementation
Status: Ready (multi-commit; medium-large; touches the live rotation path)
Purpose: Work order for P4 / 2b — collapse account-episode rotation and sleeve champion/challenger
onto the single decision-score contract, book-keyed, and reduce the rotation module sprawl. Ordered
phases, each a green commit.
Initiative: P4 (Converge accounts & sleeves) — sub-feature 2b
Estimate: M–L
Created: 2026-07-07
Last Reviewed: 2026-07-07
Related: [P4 Work Order](p4-convergence.md), [Convergence Plan](../sleeves-accounts-convergence.md),
[Decisions](../decisions.md), [Architecture Conventions](../architecture/architecture-conventions.md),
[Implementation README](README.md)

> Follows the P1/P3/2a house style. 2b is the **selection** spine of the convergence: one rotation
> path — champion/challenger on the decision-score contract — that both a plain account (its default
> book) and a sleeve (its bridging book) use, with no "account mode vs sleeve mode" branching. It is
> **behavior-affecting on the live rotation path**; steps are ordered and each is its own green commit.

## 1. Objective

Replace the two rotation paradigms —

- **account-episode rotation** (`auto_trading/rotation.py` → `select_optimal_strategy`, backed by
  `backtest_returns` + `rotation_episodes`), and
- **sleeve champion/challenger** (`sleeves/rotation.py` → `evaluate_champion_challenger_rotation`,
  backed by the decision-score contract + `rotation_decisions`)

— with **one book-keyed champion/challenger rotation** scored by the decision-score contract, and
retire the dead regime/overlay selection subsystem. A plain account rotates its **default book**; a
sleeve rotates its **bridging book** — the same code path.

### Definition of Done (2b)
- [ ] The dead regime/overlay selection subsystem is removed (see §5 — provably unused).
- [ ] Account rotation selects via the champion/challenger + decision-score model, book-keyed,
      writing `rotation_decisions` (not `rotation_episodes`).
- [ ] One rotation service is shared by account (default book) and sleeve (bridging book); the
      `auto_trading/rotation*.py` + `sleeves/rotation.py` + `shadow_evaluation.py` sprawl is reduced.
- [ ] The account-episode path (`rotation_episodes`, `sync_rotation_episode`) is retired; the
      `rotation_episodes` table is dropped (greenfield).
- [ ] Rotation cadence/trigger (when to rotate) is preserved and unified (interval/schedule + cooldown).
- [ ] P5 naming pass: `sleeve_*` rotation vocabulary → `book_*`; the two "rotation" meanings are
      disambiguated; `shadow_evaluation` renamed to its candidate-enumeration role.
- [ ] `python -m scripts.run_checks ci` green. Convergence-plan progress log appended.

## 2. Preconditions
- Branch off the latest `develop` (2a + 2c merged; submission/accounting fully on the clean book
  schema). `./.venv` exists.
- Read `docs/architecture/architecture-conventions.md` before touching rotation.
- Decisions in §5 are locked (this guide encodes the 2026-07-07 investigation + decision).

## 3. Guardrails (behavior-affecting)
- The **decision-score contract** (`domain/evaluation_decision_score.py`) and the champion/challenger
  **policy** (`domain/sleeve_rotation.py`) are the survivors — reuse them; do not re-derive the
  scoring math.
- Rotation **cadence** (interval/schedule/cooldown — "when") is orthogonal to **selection** ("what");
  keep them separable when unifying.
- Retire only rotation's **consumption** of the news/social/policy feature providers. The providers
  and the alternative strategies that use them (`policy_regime`, `news_sentiment`, `social_trend`
  signal functions in `domain/strategy_signals.py`) **stay**.
- Account columns are append-only (migration system) — the now-dead `rotation_regime_strategy_*` /
  `rotation_overlay_*` account columns are **left in place** (dead, not dropped); only the code that
  reads them retires. Table drops (`rotation_episodes`) follow the greenfield pattern.
- If a step needs a decision not covered by §5 → stop and report; do not improvise on the live path.

## 4. Branch & commit strategy
- Dedicated branch (`features/phase4-2b-unified-rotation`). One commit per phase; never commit on red.
- Commit message: summary + body + the executing model's own `Co-Authored-By` line.

## 5. Design decisions resolved
- **Champion/challenger survives; account-episode retires.** *(P4 §5 lean, confirmed 2b.)*
- **Regime/overlay selection is retired (full collapse).** Investigation of the live DB (2026-07-07):
  all 8 accounts have `rotation_overlay_mode='none'`, no `rotation_regime_strategy_*`, and none in
  `rotation_mode='regime'`; no profile configures them. `select_regime_strategy` + the overlay voting
  are unreachable dead code. *(Decided 2026-07-07 after "investigate usage first".)*
- **A plain account rotates its default book; a sleeve rotates its bridging book** — one book-keyed
  path (book-as-the-unit, per ADR 003 + the convergence plan).
- **The used account selection is already performance-based** (`select_optimal_strategy`: best
  strategy from the schedule via `backtest_returns` + closed episodes) — it maps cleanly onto
  champion/challenger; the difference is the data source (backtest returns/episodes → the
  decision-score contract + `rotation_decisions`).
- **Feature providers stay** — they back alternative strategies, not just rotation.

## 6. Current-state map (evidence)
| Concern | Account path | Sleeve path (survivor) |
|---|---|---|
| Selection | `select_optimal_strategy` (backtest returns + episodes) | `evaluate_champion_challenger_rotation` (decision-score) |
| Candidate set | `rotation_schedule` | `shadow_evaluation` (schedule → candidates) |
| Decision record | `rotation_episodes` | `rotation_decisions` |
| Cadence | `is_rotation_due` (interval/schedule, `rotation_mode`) | cooldown |
| Regime/overlays | `select_regime_strategy` + overlay voting | — |
| Modules | `auto_trading/rotation.py`, `runtime_rotation.py`, `rotation_bridge.py`, `domain/rotation.py` | `sleeves/rotation.py`, `shadow_evaluation.py`, `domain/sleeve_rotation.py` |

## 7. Build plan (ordered; each a green commit)

### Phase 2b-1 — Retire the dead regime/overlay selection subsystem  **[light]**
- Remove `select_regime_strategy`, `classify_policy_regime`, the overlay voting
  (`select_rotation_overlay_direction`, `apply_rotation_overlay_to_regime`,
  `_classify_news/social_overlay_vote`), `fetch_rotation_overlay_tickers`, and the `mode == "regime"`
  branch in `select_account_rotation_strategy` (+ its runtime wrappers). Keep the feature providers +
  alternative-strategy signal functions.
- Leave the dead `rotation_regime_strategy_*` / `rotation_overlay_*` account columns (append-only).
- Check: `run_suite src/trading/services/auto_trading` green; remove now-dead tests.

### Phase 2b-2 — Book-keyed candidate enumeration (absorb `shadow_evaluation`)  **[strong]**
- Generalize the sleeve candidate enumeration (`build_sleeve_shadow_evaluation`) into a book-keyed
  candidate step: given a book + its strategy schedule, produce incumbent + challenger candidates with
  decision scores. A plain account's default book uses the account `rotation_schedule`.
- Check: candidate-enumeration unit tests for both a default book and a sleeve book.

### Phase 2b-3 — Route account selection through champion/challenger  **[strong]**
- Replace the account `select_optimal_strategy` call in the runtime with the champion/challenger
  decision (2b-2 candidates → `evaluate_champion_challenger_rotation`), writing `rotation_decisions`
  keyed on the default book. Preserve the cadence trigger (interval/schedule) as the "when".
- Check: `run_suite src/trading/services/auto_trading` green (account rotation writes
  `rotation_decisions`, selects the best decision-score strategy).

### Phase 2b-4 — Book-native evidence, one rotation service, retire the episode path  **[strong]**

**Scope revision (2026-07-07):** investigation found `rotation_episodes` is *not* rotation-internal
accounting — it is the **evaluation subsystem's strategy-isolated paper-live evidence store**
(`evaluation/evidence.py::build_paper_live_evidence` → `compute_blended_score`), and for a
rotation-enabled account it is the *only* paper-live source (no snapshot fallback). Dropping it
blindly would strip the live half of the decision score for exactly the accounts that rotate. Per the
"stop and report if bigger" guardrail this was surfaced; the user chose to make evidence **book-native**
(book snapshots + `rotation_decisions`) and then retire episodes. 2b-4 is therefore split:

- **2b-4a — Book-native paper-live evidence.** Re-point `build_paper_live_evidence` off
  `rotation_episodes` onto the account's default-book `equity_snapshots` sliced at the strategy
  boundaries recorded in `rotation_decisions` (each decision logs incumbent→selected). Reproduces the
  per-strategy windows episodes gave; cold start = the active strategy since inception. Keep the
  episode table intact this step. Check: `run_suite src/trading/services/evaluation` + full `run_checks ci`.
- **2b-4b — One book-keyed rotation service.** Collapse the account + sleeve selection/apply into one
  book-keyed service; reduce the `auto_trading/rotation*.py` + `sleeves/rotation.py` sprawl; retire the
  dead `select_optimal_strategy` path + its backtest/episode DI threading. Land cadence unification
  (interval/schedule trigger + cooldown guard). Check: full `run_checks ci`.
- **2b-4c — Retire the episode path.** With no remaining reader, retire `sync_rotation_episode` /
  `rotate_account_if_due` episode logic / `RotationEpisodeRepository` / episode-only
  `compute_live_account_metrics`, and drop `rotation_episodes` (greenfield: remove CREATE + indexes +
  migration keys). Check: full `run_checks ci` green.

### Phase 2b-5 — P5 naming pass  **[light]**
- Rename `sleeve_*` rotation vocabulary to `book_*` (domain + services), disambiguate the two
  "rotation" meanings (cadence vs selection), and rename `shadow_evaluation` to its candidate-
  enumeration role. Update `docs/adr` / maps as needed.
- Check: full `run_checks ci` green; docs/maps in sync.

## 8. Open design points (resolve in-phase; stop and report if bigger)
- **Cadence unification:** account uses interval/schedule (`is_rotation_due`); sleeve uses cooldown.
  2b-3 kept the account cadence as the "when" (cooldown inactive); **2b-4b** lands the unified
  "cadence trigger + cooldown guard".
- **`rotation_decisions` for a plain account's default book:** ✅ resolved (2b-3) — the table is
  `book_id`-keyed under the clean schema; a default book slots in directly via `insert_for_book`.
- **`rotation_episodes` is evaluation evidence, not rotation accounting:** ✅ resolved (2b-4a) —
  paper-live evidence is now book-native (default-book `equity_snapshots` sliced at `rotation_decisions`
  boundaries), so the episode table can be dropped in 2b-4c without losing the decision score's live half.
- **Cross-book vs per-book rotation:** a sleeved account rotates each sleeve book; a plain account
  rotates its one default book — confirm no account-level aggregate rotation is lost.

## 9. Validation
```
.venv\Scripts\python.exe -m scripts.checks.run_suite src/trading/services/auto_trading src/trading/services/sleeves --no-cov
.venv\Scripts\python.exe -m scripts.checks.repo.layer_check
.venv\Scripts\python.exe -m scripts.checks.python.mypy_check
.venv\Scripts\python.exe -m scripts.run_checks ci      # final, per phase where feasible
```

## 10. Out of scope
- Submission (2a) and accounting (2c) — done.
- Broker/environment axis — already converged.
- The unified parameter-source cleanup (param sprawl across stores) — tracked as a later plan item (P7).
