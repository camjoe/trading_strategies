from __future__ import annotations

from trading.backtesting.domain.risk_warnings import build_backtest_warnings


def _account(**overrides):
    account = {
        "risk_policy": "none",
        "instrument_mode": "equity",
    }
    account.update(overrides)
    return account


def test_build_backtest_warnings_base_warnings_always_present() -> None:
    warnings = build_backtest_warnings(_account(), allow_approximate_leaps=False)

    assert any("adjusted daily close data only" in warning for warning in warnings)
    assert any("survivorship bias" in warning for warning in warnings)


def test_build_backtest_warnings_adds_risk_policy_warning() -> None:
    warnings = build_backtest_warnings(_account(risk_policy="fixed_stop"), allow_approximate_leaps=False)

    assert any("Stop-loss/take-profit checks" in warning for warning in warnings)


def test_build_backtest_warnings_handles_leaps_opt_in_flag() -> None:
    warnings_without_opt_in = build_backtest_warnings(
        _account(instrument_mode="leaps"),
        allow_approximate_leaps=False,
    )
    assert any("LEAPs mode is approximated" in warning for warning in warnings_without_opt_in)
    assert any("opt-in was not enabled" in warning for warning in warnings_without_opt_in)

    warnings_with_opt_in = build_backtest_warnings(
        _account(instrument_mode="leaps"),
        allow_approximate_leaps=True,
    )
    assert any("LEAPs mode is approximated" in warning for warning in warnings_with_opt_in)
    assert not any("opt-in was not enabled" in warning for warning in warnings_with_opt_in)
