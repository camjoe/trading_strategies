import pytest

from tests.support.reporting import insert_trade, make_evaluation_artifact
from trading.models import AccountConfig
from trading.services.accounts.mutations import create_account, get_account
from trading.services.reporting.comparison import compare_strategies


def test_compare_strategies_outputs_summary_and_truncates_positions(
    conn, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    create_account(conn, "acct_many", "Trend", 10000.0, "SPY", config=AccountConfig(descriptive_name="Many"))
    account = get_account(conn, "acct_many")

    tickers = ["AAPL", "AMZN", "GOOG", "META", "MSFT", "NVDA"]
    for index, ticker in enumerate(tickers):
        insert_trade(conn, account["id"], ticker, 1.0, 100.0 + index, trade_time=f"2026-01-01T00:00:0{index}Z")
    conn.commit()

    monkeypatch.setattr(
        "trading.services.analysis.portfolio.fetch_latest_prices",
        lambda symbols, **_kwargs: {symbol: 110.0 for symbol in symbols},
    )
    monkeypatch.setattr(
        "trading.services.analysis.portfolio.benchmark_stats", lambda *_args, **_kwargs: (10100.0, 1.0)
    )
    monkeypatch.setattr(
        "trading.services.reporting.comparison.fetch_strategy_evaluation_for_account_row",
        lambda *_args, **_kwargs: make_evaluation_artifact(
            account_id=account["id"],
            account_name="acct_many",
        ),
    )
    monkeypatch.setattr("trading.services.reporting.comparison.infer_overall_trend", lambda *_args, **_kwargs: "up")

    compare_strategies(conn, lookback=5)
    out = capsys.readouterr().out
    assert "Account policy comparison (current paper account state):" in out
    assert "display_name=Many" in out
    assert "positions: AAPL:1.00, AMZN:1.00, GOOG:1.00, META:1.00, MSFT:1.00, ..." in out


def test_compare_strategies_handles_empty_accounts_and_no_positions(
    conn, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    compare_strategies(conn, lookback=5)
    assert "No paper accounts found." in capsys.readouterr().out

    create_account(conn, "acct_none", "Trend", 1000.0, "SPY", config=AccountConfig(descriptive_name="No Trades"))
    monkeypatch.setattr("trading.services.analysis.portfolio.benchmark_stats", lambda *_args, **_kwargs: (None, None))

    compare_strategies(conn, lookback=5)
    out = capsys.readouterr().out
    assert "positions: none" in out
