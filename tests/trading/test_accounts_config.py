import pytest

from trading.accounts import configure_account, create_account, get_account
from trading.models import AccountConfig


def test_configure_account_updates_risk_and_option_fields(conn) -> None:
    create_account(conn, "acct_cfg", "Trend", 5000.0, "SPY")

    configure_account(
        conn,
        account_name="acct_cfg",
        config=AccountConfig(
            risk_policy="stop_and_target",
            stop_loss_pct=5.0,
            take_profit_pct=10.0,
            instrument_mode="leaps",
            option_strike_offset_pct=4.0,
            option_min_dte=150,
            option_max_dte=365,
        ),
    )

    account = get_account(conn, "acct_cfg")
    assert account["risk_policy"] == "stop_and_target"
    assert float(account["stop_loss_pct"]) == pytest.approx(5.0)
    assert float(account["take_profit_pct"]) == pytest.approx(10.0)
    assert account["instrument_mode"] == "leaps"
    assert float(account["option_strike_offset_pct"]) == pytest.approx(4.0)
    assert int(account["option_min_dte"]) == 150
    assert int(account["option_max_dte"]) == 365


def test_create_account_rejects_invalid_option_dte_range(conn) -> None:
    with pytest.raises(ValueError, match="option_min_dte cannot be greater than option_max_dte"):
        create_account(
            conn,
            name="bad_dte",
            strategy="Test",
            initial_cash=5000,
            benchmark_ticker="SPY",
            config=AccountConfig(
                instrument_mode="leaps",
                option_min_dte=365,
                option_max_dte=120,
            ),
        )


def test_configure_account_rejects_invalid_iv_rank_range(conn) -> None:
    create_account(conn, "acct_bad_iv", "Trend", 5000.0, "SPY")

    with pytest.raises(ValueError, match="iv_rank_min cannot be greater than iv_rank_max"):
        configure_account(
            conn,
            account_name="acct_bad_iv",
            config=AccountConfig(iv_rank_min=80, iv_rank_max=20),
        )


def test_configure_account_rejects_invalid_delta_bounds(conn) -> None:
    create_account(conn, "acct_bad_delta", "Trend", 5000.0, "SPY")

    with pytest.raises(ValueError, match="target_delta_min must be between 0 and 1"):
        configure_account(
            conn,
            account_name="acct_bad_delta",
            config=AccountConfig(target_delta_min=1.2),
        )
