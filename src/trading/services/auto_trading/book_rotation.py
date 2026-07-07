"""Book-keyed champion/challenger rotation selection for accounts.

Routes a plain account's rotation *selection* through the same decision-score
champion/challenger model the sleeve path uses. Given the account's default book,
the incumbent (its active strategy) and challengers (its rotation schedule) are
enumerated on the decision-score contract (2b-2), the champion/challenger policy
picks the winner, and the decision is recorded on the default book's
``rotation_decisions``.

Scope (2b-3): this owns the "what" — which strategy. The cadence trigger
(interval/schedule) stays in ``rotate_account_if_due`` as the "when"; cooldown is
left inactive here because the account cadence already governs spacing. Collapsing
the account and sleeve paths into one service, unifying cooldown, and retiring the
episode path are 2b-4 work.
"""

from __future__ import annotations

import json
import sqlite3

from common.coercion import row_expect_int
from trading.domain.rotation import parse_rotation_schedule, resolve_active_strategy
from trading.domain.sleeve_rotation import evaluate_champion_challenger_rotation
from trading.models import AccountRecord
from trading.models.sleeves.sleeve_rotation_score_weights import SleeveRotationScoreWeights
from trading.repositories.book_bridge import default_book_id
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.repositories.strategy_param_sets import StrategyParamSetRepository
from trading.services.auto_trading.rotation_candidates import build_book_rotation_candidates
from trading.services.sleeves.rotation import SleeveRotationConfig


def _weights_from_config(config: SleeveRotationConfig) -> SleeveRotationScoreWeights:
    return SleeveRotationScoreWeights(
        risk_adjusted_return_weight=float(config.risk_adjusted_return_weight),
        stability_weight=float(config.stability_weight),
        drawdown_penalty_weight=float(config.drawdown_penalty_weight),
        cost_penalty_weight=float(config.cost_penalty_weight),
        regime_fit_weight=float(config.regime_fit_weight),
    )


def evaluate_account_rotation_decision(
    conn: sqlite3.Connection,
    account: AccountRecord,
    as_of_iso: str,
    *,
    config: SleeveRotationConfig = SleeveRotationConfig(),
) -> str | None:
    """Select the account's rotation strategy via champion/challenger and record it.

    Returns the selected strategy (the winning challenger on ``rotate``, the
    incumbent on ``hold``), or ``None`` when there is no active strategy to treat as
    the incumbent. A decision row is written on the account's default book whenever
    an incumbent exists — the audit of the hold/rotate call.
    """
    incumbent_strategy = resolve_active_strategy(account)
    if not incumbent_strategy:
        return None

    schedule = [name for name in parse_rotation_schedule(account["rotation_schedule"]) if name]
    book_id = default_book_id(conn, row_expect_int(account, "id"))

    param_set_repo = StrategyParamSetRepository(conn)
    incumbent_param_set = param_set_repo.fetch_active(strategy_name=incumbent_strategy)
    candidates = build_book_rotation_candidates(
        conn,
        book_id=book_id,
        account=account,
        incumbent_strategy=incumbent_strategy,
        incumbent_param_set_id=incumbent_param_set.id if incumbent_param_set is not None else None,
        schedule=schedule,
    )

    decision = evaluate_champion_challenger_rotation(
        incumbent=candidates.incumbent,
        challengers=candidates.challengers,
        min_trades_in_window=max(1, int(config.min_trades_in_window)),
        outperformance_threshold_bps=float(config.outperformance_threshold_bps),
        # The account cadence (interval/schedule) is the "when"; cooldown unification
        # with the sleeve path is deferred to 2b-4.
        cooldown_active=False,
        weights=_weights_from_config(config),
    )

    RotationDecisionRepository(conn).insert_for_book(
        book_id=book_id,
        decision_time=as_of_iso,
        incumbent_strategy=decision.incumbent_strategy,
        challenger_strategy=decision.challenger_strategy,
        selected_strategy=decision.selected_strategy,
        rotation_action=decision.rotation_action,
        cooldown_active=1 if decision.cooldown_active else 0,
        score_components_json=json.dumps(decision.score_components, sort_keys=True),
        gate_results_json=json.dumps(decision.gate_results, sort_keys=True),
        decision_reason=decision.decision_reason,
        config_version=config.config_version,
        created_at=as_of_iso,
    )
    return decision.selected_strategy
