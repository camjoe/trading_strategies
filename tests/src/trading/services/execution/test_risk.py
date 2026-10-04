from __future__ import annotations

from types import SimpleNamespace

import pytest

from trading.services.execution.risk import build_risk_snapshot, compute_current_exposure_snapshot


def test_compute_current_exposure_snapshot_uses_injected_symbol_sector_map() -> None:
    positions = [
        SimpleNamespace(symbol="AAPL", market_value=300.0),
        SimpleNamespace(symbol="MSFT", market_value=200.0),
        SimpleNamespace(symbol="JPM", market_value=100.0),
    ]
    books = [SimpleNamespace(current_equity=1_000.0)]

    gross, net, max_symbol_pct, max_sector_pct, total_equity = compute_current_exposure_snapshot(
        position_rows=positions,
        book_rows=books,
        symbol_sector_map={"AAPL": "technology", "MSFT": "technology", "JPM": "financials"},
    )

    assert gross == 600.0
    assert net == 600.0
    assert max_symbol_pct == 0.3
    assert max_sector_pct == 0.5
    assert total_equity == 1_000.0


def _snapshot(
    *,
    current_equity: float,
    peak_equity: float | None,
    positions: list[SimpleNamespace] | None = None,
):
    return build_risk_snapshot(
        account_id=1,
        snapshot_time="2026-07-26T00:00:00Z",
        kill_switch_triggered=False,
        payload={},
        position_rows=positions or [],
        book_rows=[SimpleNamespace(current_equity=current_equity)],
        peak_equity=peak_equity,
        symbol_sector_map={},
    )


def test_build_risk_snapshot_computes_point_in_time_drawdown_below_peak() -> None:
    assert _snapshot(current_equity=900.0, peak_equity=1_000.0).drawdown_pct == pytest.approx(-10.0)


def test_build_risk_snapshot_reads_zero_drawdown_at_a_new_peak() -> None:
    assert _snapshot(current_equity=1_100.0, peak_equity=1_000.0).drawdown_pct == 0.0


def test_build_risk_snapshot_drawdown_is_none_with_no_equity_history() -> None:
    assert _snapshot(current_equity=1_000.0, peak_equity=None).drawdown_pct == 0.0


def test_build_risk_snapshot_leverage_proxy_is_gross_over_equity() -> None:
    assert _snapshot(current_equity=500.0, peak_equity=500.0).leverage_proxy == 0.0

    leveraged = _snapshot(
        current_equity=500.0,
        peak_equity=500.0,
        positions=[SimpleNamespace(symbol="AAPL", market_value=750.0)],
    )
    assert leveraged.leverage_proxy == 1.5


def test_build_risk_snapshot_daily_loss_pct_stays_none() -> None:
    # Single-day peak-to-trough still needs intraday equity ticks; only
    # drawdown_pct (point-in-time from the historical peak) is computable today.
    assert _snapshot(current_equity=900.0, peak_equity=1_000.0).daily_loss_pct is None
