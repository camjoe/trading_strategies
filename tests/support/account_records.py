from __future__ import annotations

from trading.models import AccountRecord


def make_account_record(**overrides: object) -> AccountRecord:
    """Build an ``AccountRecord`` test fixture with sensible defaults.

    Tests can override only the fields they care about while keeping a complete,
    production-shaped account row.
    """

    values: dict[str, object] = {
        "id": 1,
        "name": "acct-sample",
        "account_kind": "managed",
        "strategy": "trend",
        "initial_cash": 1000.0,
        "created_at": "2026-01-01T00:00:00Z",
        "benchmark_ticker": "SPY",
        "descriptive_name": "Sample Account",
        "goal_min_return_pct": None,
        "goal_max_return_pct": None,
        "goal_period": "monthly",
        # Execution settings are book columns since revision 0004 — they are
        # no longer part of the account row.
        "option_strike_offset_pct": None,
        "option_min_dte": None,
        "option_max_dte": None,
        "option_type": None,
        "target_delta_min": None,
        "target_delta_max": None,
        "max_premium_per_trade": None,
        "max_contracts_per_trade": None,
        "iv_rank_min": None,
        "iv_rank_max": None,
        "roll_dte_threshold": None,
        "broker_type": "paper",
        "broker_host": None,
        "broker_port": None,
        "broker_client_id": None,
        # SAFETY: tests must never opt into live trading by default.
        "live_trading_enabled": 0,
        "trade_universes": None,
    }
    values.update(overrides)
    return AccountRecord.from_mapping(values)


__all__ = ["make_account_record"]
