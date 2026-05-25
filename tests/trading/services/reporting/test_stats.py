import pytest

from trading.models import AccountConfig
from trading.services.accounts import create_account, get_account
from trading.services.reporting import build_account_stats, format_goal_text, infer_overall_trend
from tests.support.reporting import insert_snapshot, insert_trade
from tests.support.seed.db import ACCT_MOMENTUM


def test_build_account_stats_uses_price_map(reporting_account, conn, monkeypatch: pytest.MonkeyPatch) -> None:
    insert_trade(conn, reporting_account["id"], "AAPL", 2.0, 100.0)
    conn.commit()

    monkeypatch.setattr(
        "trading.services.reporting.stats.fetch_latest_prices",
        lambda _tickers: {"AAPL": 120.0},
    )

    state, prices, market_value, unrealized, equity = build_account_stats(conn, reporting_account)

    assert state.cash == pytest.approx(800.0)
    assert prices == {"AAPL": 120.0}
    assert market_value == pytest.approx(240.0)
    assert unrealized == pytest.approx(40.0)
    assert equity == pytest.approx(1040.0)


def test_build_account_stats_ignores_positions_without_price(reporting_account, conn, monkeypatch: pytest.MonkeyPatch) -> None:
    insert_trade(conn, reporting_account["id"], "AAPL", 2.0, 100.0)
    insert_trade(conn, reporting_account["id"], "MSFT", 1.0, 50.0, trade_time="2026-01-01T00:00:01Z")
    conn.commit()

    monkeypatch.setattr(
        "trading.services.reporting.stats.fetch_latest_prices",
        lambda _tickers: {"AAPL": 120.0},
    )

    state, prices, market_value, unrealized, equity = build_account_stats(conn, reporting_account)

    assert state.cash == pytest.approx(750.0)
    assert prices == {"AAPL": 120.0}
    assert market_value == pytest.approx(240.0)
    assert unrealized == pytest.approx(40.0)
    assert equity == pytest.approx(990.0)


@pytest.mark.parametrize(
    ("history", "current_equity", "expected"),
    [
        ([980.0, 1000.0, 1015.0], 1030.0, "up"),
        ([1000.0, 995.0, 990.0], 980.0, "down"),
        ([1000.0, 995.0, 990.0], 991.0, "flat"),
    ],
)
def test_infer_overall_trend_uses_snapshot_history(reporting_account, conn, history, current_equity: float, expected: str) -> None:
    for index, equity in enumerate(history, start=1):
        insert_snapshot(conn, reporting_account["id"], f"2026-01-0{index}T00:00:00Z", equity)
    conn.commit()

    assert infer_overall_trend(conn, reporting_account["id"], current_equity=current_equity, lookback=10) == expected


def test_infer_overall_trend_returns_insufficient_data_without_enough_points(seeded_conn) -> None:
    account = get_account(seeded_conn, ACCT_MOMENTUM)  # seeded with no snapshots

    assert infer_overall_trend(seeded_conn, account["id"], current_equity=1000.0, lookback=10) == "insufficient-data"


def test_infer_overall_trend_returns_insufficient_data_when_first_equity_is_zero(conn) -> None:
    create_account(conn, "acct_zero", "Trend", 1000.0, "SPY")
    account = get_account(conn, "acct_zero")

    insert_snapshot(conn, account["id"], "2026-02-01T00:00:00Z", 0.0)
    insert_snapshot(conn, account["id"], "2026-02-02T00:00:00Z", 10.0)
    conn.commit()

    assert infer_overall_trend(conn, account["id"], current_equity=20.0, lookback=10) == "insufficient-data"


@pytest.mark.parametrize(
    ("goal_min", "goal_max", "goal_period", "expected"),
    [
        (None, None, "monthly", "not-set"),
        (1.5, 3.5, "weekly", "1.50% to 3.50% per weekly"),
        (2.0, None, "monthly", ">= 2.00% per monthly"),
        (None, 4.0, "quarterly", "<= 4.00% per quarterly"),
    ],
)
def test_format_goal_text_variants(conn, goal_min, goal_max, goal_period, expected: str) -> None:
    create_account(
        conn,
        "acct_goal",
        "Trend",
        1000.0,
        "SPY",
        config=AccountConfig(
            goal_min_return_pct=goal_min,
            goal_max_return_pct=goal_max,
            goal_period=goal_period,
        ),
    )
    account = get_account(conn, "acct_goal")
    assert format_goal_text(account) == expected
