from __future__ import annotations

from paper_trading_ui.backend.services import test_account as services_test_account
from paper_trading_ui.backend.config import TEST_ACCOUNT_NAME, TEST_BACKTEST_ACCOUNT_NAME


def test_test_account_parsing_and_payloads(monkeypatch, tmp_path) -> None:
    investments_file = tmp_path / "test_investments.txt"
    investments_file.write_text(
        "\n".join(
            [
                "benchmark: qqq",
                "- [x] AAPL ($1,500 - core)",
                "- [ ] TSLA ($300)",
                "- [x] MSFT",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(services_test_account, "TEST_INVESTMENTS_CANDIDATES", (investments_file,))

    rows = services_test_account.parse_test_investments()
    assert rows == [{"ticker": "AAPL", "amount": 1500.0}, {"ticker": "MSFT", "amount": 0.0}]
    assert services_test_account.compute_test_account_equity(rows) == 1500.0
    assert services_test_account.parse_test_account_benchmark() == "QQQ"

    summary = services_test_account.build_test_account_summary()
    assert summary["name"] == TEST_ACCOUNT_NAME
    assert summary["benchmark"] == "QQQ"
    assert summary["equity"] == 1500.0

    detail = services_test_account.build_test_account_detail_payload()
    assert detail["latestBacktest"] is None
    assert len(detail["trades"]) == 2
    assert detail["snapshots"][0]["equity"] == 1500.0


def test_resolve_backtest_account_name_and_payload_resolver(conn, monkeypatch) -> None:
    assert services_test_account.resolve_backtest_account_name(TEST_ACCOUNT_NAME) == TEST_BACKTEST_ACCOUNT_NAME
    assert services_test_account.resolve_backtest_account_name("acct_live") == "acct_live"

    calls: list[str] = []
    monkeypatch.setattr(
        services_test_account,
        "ensure_test_backtest_account",
        lambda _conn: calls.append("called"),
    )

    resolved = services_test_account.resolve_backtest_payload_account(TEST_ACCOUNT_NAME, conn)
    assert resolved == TEST_BACKTEST_ACCOUNT_NAME
    assert calls == ["called"]


def test_ensure_test_backtest_account_creates_shadow_account_with_min_cash(conn, monkeypatch) -> None:
    monkeypatch.setattr(services_test_account, "compute_test_account_equity", lambda _rows=None: 0.0)
    monkeypatch.setattr(services_test_account, "parse_test_account_benchmark", lambda: "QQQ")

    services_test_account.ensure_test_backtest_account(conn)

    row = conn.execute(
        "SELECT name, initial_cash, benchmark_ticker FROM accounts WHERE name = ?",
        (TEST_BACKTEST_ACCOUNT_NAME,),
    ).fetchone()
    assert row is not None
    assert row["name"] == TEST_BACKTEST_ACCOUNT_NAME
    assert float(row["initial_cash"]) == 1.0
    assert row["benchmark_ticker"] == "QQQ"
