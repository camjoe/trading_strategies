from __future__ import annotations

import pytest
from paper_trading_web.backend.services.accounts import summaries as account_summaries

from tests.support.account_records import make_account_record
from trading.models.accounts import AccountState
from trading.models.portfolio import EquitySnapshotRecord


def _account_record(**overrides: object):
    values: dict[str, object] = {
        "name": "acct_default",
        "descriptive_name": "Default Account",
    }
    values.update(overrides)
    return make_account_record(**values)


def _make_state(
    positions: dict[str, float],
    avg_cost: dict[str, float],
    *,
    cash: float = 0.0,
    realized_pnl: float = 0.0,
    total_deposited: float = 0.0,
) -> AccountState:
    return AccountState(
        cash=cash,
        positions=positions,
        avg_cost=avg_cost,
        realized_pnl=realized_pnl,
        total_deposited=total_deposited,
    )


def _stats_stub(equity: float):
    """Stand in for ``build_account_stats``: an all-cash account at ``equity``."""
    return lambda _conn, _row, **_kwargs: (_make_state({}, {}, cash=equity), {}, 0.0, 0.0, equity)


def _patch_book_reads(
    monkeypatch,
    *,
    rotation=None,
    active_strategy: str = "trend",
) -> None:
    """Stub the book-owned rotation/assignment reads (ADR 014) for conn=None tests."""
    from trading.services.books.rotation.engine import BookRotationScheduleConfig

    monkeypatch.setattr(
        account_summaries,
        "resolve_default_book_rotation_schedule",
        lambda _conn, *, account_id: rotation or BookRotationScheduleConfig(),
    )
    monkeypatch.setattr(
        account_summaries,
        "active_strategy_for_account",
        lambda _conn, _account_id: active_strategy,
    )
    # Execution settings are book columns (revision 0004); conn=None tests
    # stub the default-book read (None -> code defaults in the summary).
    monkeypatch.setattr(
        account_summaries,
        "get_default_book",
        lambda _conn, *, account_id: None,
    )


def test_build_account_summary_uses_snapshot_delta(monkeypatch) -> None:
    _patch_book_reads(monkeypatch)
    monkeypatch.setattr(
        account_summaries,
        "build_account_stats",
        _stats_stub(1200.0),
    )
    monkeypatch.setattr(
        account_summaries,
        "get_latest_account_snapshot",
        lambda _conn, _account_id: EquitySnapshotRecord(
            id=1,
            account_id=1,
            book_id=None,
            snapshot_time="2026-01-02T00:00:00Z",
            cash=0.0,
            market_value=1100.0,
            equity=1100.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
        ),
    )

    summary = account_summaries.build_account_summary(
        conn=None,
        row=_account_record(
            name="acct_a",
            descriptive_name="Account A",
        ),
    )

    assert summary["equity"] == 1200.0
    assert summary["brokerType"] == "paper"
    assert summary["totalChange"] == 200.0
    assert summary["totalChangePct"] == pytest.approx(20.0)
    assert summary["changeSinceLastSnapshot"] == 100.0


def test_build_account_list_payload_maps_summary_fields() -> None:
    payload = account_summaries.build_account_list_payload(
        {
            "name": "acct_one",
            "displayName": "Account One",
            "strategy": "trend",
            "instrumentMode": "equity",
            "benchmark": "SPY",
            "equity": 1000.0,
            "totalChange": 0.0,
            "totalChangePct": 0.0,
            "changeSinceLastSnapshot": None,
            "latestSnapshotTime": None,
        }
    )
    assert payload["name"] == "acct_one"
    assert payload["strategy"] == "trend"


def test_build_comparison_account_payload_includes_live_overlay_summary() -> None:
    payload = account_summaries.build_comparison_account_payload(
        {
            "name": "acct_cmp",
            "displayName": "Acct Compare",
            "strategy": "trend",
            "benchmark": "SPY",
            "equity": 1100.0,
            "initialCash": 1000.0,
            "totalChange": 100.0,
            "totalChangePct": 10.0,
            "liveBenchmarkReturnPct": 7.0,
            "liveAlphaPct": 3.0,
        },
        None,
        {
            "blendedScore": 4.5,
            "overallConfidence": 0.8,
            "backtestConfidence": 1.0,
            "paperLiveConfidence": 0.6,
            "dataGaps": ["missing_walk_forward_evidence"],
        },
    )

    assert payload["liveBenchmarkReturnPct"] == pytest.approx(7.0)
    assert payload["liveAlphaPct"] == pytest.approx(3.0)
    assert payload["evaluation"]["blendedScore"] == pytest.approx(4.5)


class TestBuildPositionsFromStats:
    def test_missing_price_skips_position(self) -> None:
        state = _make_state({"AAPL": 5.0}, {"AAPL": 100.0})
        positions = account_summaries._build_positions_from_stats(state, {})
        assert positions == []

    def test_partial_prices_skips_only_missing(self) -> None:
        state = _make_state({"AAPL": 2.0, "MSFT": 3.0}, {"AAPL": 100.0, "MSFT": 200.0})
        positions = account_summaries._build_positions_from_stats(state, {"AAPL": 110.0})
        tickers = [item["ticker"] for item in positions]
        assert tickers == ["AAPL"]
        assert "MSFT" not in tickers

    def test_unrealized_pnl_formula(self) -> None:
        state = _make_state({"AAPL": 4.0}, {"AAPL": 100.0})
        positions = account_summaries._build_positions_from_stats(state, {"AAPL": 110.0})
        assert len(positions) == 1
        pos = positions[0]
        assert pos["unrealizedPnl"] == pytest.approx((110.0 - 100.0) * 4.0)
        assert pos["marketValue"] == pytest.approx(110.0 * 4.0)
        assert pos["avgCost"] == pytest.approx(100.0)

    def test_settlement_ticker_excluded(self) -> None:
        from common.constants import SETTLEMENT_TICKER

        state = _make_state(
            {"AAPL": 2.0, SETTLEMENT_TICKER: 500.0},
            {"AAPL": 100.0},
        )
        positions = account_summaries._build_positions_from_stats(
            state,
            {"AAPL": 105.0, SETTLEMENT_TICKER: 1.0},
        )
        tickers = [item["ticker"] for item in positions]
        assert SETTLEMENT_TICKER not in tickers
        assert "AAPL" in tickers

    def test_zero_qty_excluded(self) -> None:
        state = _make_state({"AAPL": 0.0, "MSFT": 2.0}, {"MSFT": 50.0})
        positions = account_summaries._build_positions_from_stats(
            state,
            {"AAPL": 100.0, "MSFT": 60.0},
        )
        assert len(positions) == 1
        assert positions[0]["ticker"] == "MSFT"

    def test_negative_unrealized_pnl_when_price_falls(self) -> None:
        state = _make_state({"AAPL": 3.0}, {"AAPL": 100.0})
        positions = account_summaries._build_positions_from_stats(state, {"AAPL": 90.0})
        assert positions[0]["unrealizedPnl"] == pytest.approx((90.0 - 100.0) * 3.0)


class TestBuildAccountSummaryShape:
    def test_required_keys_present(self, monkeypatch) -> None:
        _patch_book_reads(monkeypatch)
        monkeypatch.setattr(
            account_summaries,
            "build_account_stats",
            _stats_stub(1200.0),
        )
        monkeypatch.setattr(
            account_summaries,
            "get_latest_account_snapshot",
            lambda _conn, _account_id: None,
        )
        row = _account_record(
            name="acct_shape",
            descriptive_name="Shape Account",
        )
        summary = account_summaries.build_account_summary(conn=None, row=row)
        for key in (
            "name",
            "equity",
            "initialCash",
            "totalChange",
            "totalChangePct",
            "changeSinceLastSnapshot",
            "strategy",
        ):
            assert key in summary, f"Missing key: {key}"

    def test_rotation_keys_present_and_parsed(self, monkeypatch) -> None:
        from trading.services.books.rotation.engine import BookRotationScheduleConfig

        monkeypatch.setattr(
            account_summaries,
            "build_account_stats",
            _stats_stub(1200.0),
        )
        monkeypatch.setattr(
            account_summaries,
            "get_latest_account_snapshot",
            lambda _conn, _account_id: None,
        )
        _patch_book_reads(
            monkeypatch,
            rotation=BookRotationScheduleConfig(
                rotation_enabled=True,
                schedule=("trend", "ma_crossover", "mean_reversion"),
                lookback_days=30,
            ),
            active_strategy="ma_crossover",
        )
        row = _account_record(
            name="acct_rotation",
            descriptive_name="Rotation Account",
        )

        summary = account_summaries.build_account_summary(conn=None, row=row)
        assert summary["activeStrategy"] == "ma_crossover"
        assert summary["rotation"] == {
            "enabled": True,
            "schedule": ["trend", "ma_crossover", "mean_reversion"],
            "lookbackDays": 30,
        }

    def test_deposit_model_account_zero_initial_cash(self, monkeypatch) -> None:
        _patch_book_reads(monkeypatch)
        monkeypatch.setattr(
            account_summaries,
            "build_account_stats",
            _stats_stub(1100.0),
        )
        monkeypatch.setattr(
            account_summaries,
            "get_latest_account_snapshot",
            lambda _conn, _account_id: None,
        )
        row = _account_record(
            id=2,
            name="deposit_acct",
            descriptive_name="Deposit",
            initial_cash=0.0,
        )
        summary = account_summaries.build_account_summary(conn=None, row=row)
        assert summary["totalChangePct"] == pytest.approx(0.0)
