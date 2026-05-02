from __future__ import annotations

from paper_trading_ui.backend.services import test_account as services_test_account
from paper_trading_ui.backend.config import TEST_ACCOUNT_DISPLAY_NAME, TEST_ACCOUNT_NAME


def test_test_account_parsing_helpers(monkeypatch, tmp_path) -> None:
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

def test_fetch_resolved_account_row_uses_canonical_name(conn, monkeypatch) -> None:
    monkeypatch.setattr(services_test_account, "compute_test_account_equity", lambda _rows=None: 1000.0)
    monkeypatch.setattr(services_test_account, "parse_test_account_benchmark", lambda: "SPY")

    resolved = services_test_account.fetch_resolved_account_row(conn, TEST_ACCOUNT_NAME)
    assert resolved.name == TEST_ACCOUNT_NAME

    with conn:
        conn.execute(
            """
            INSERT INTO accounts (name, account_kind, strategy, initial_cash, created_at, benchmark_ticker, descriptive_name)
            VALUES ('acct_live', 'managed', 'trend', 1000.0, '2026-01-01T00:00:00Z', 'SPY', 'Live')
            """
        )
    resolved_non_test = services_test_account.fetch_resolved_account_row(conn, "acct_live")
    assert resolved_non_test.name == "acct_live"


def test_ensure_test_account_creates_manual_only_account_with_min_cash(conn, monkeypatch) -> None:
    monkeypatch.setattr(services_test_account, "compute_test_account_equity", lambda _rows=None: 0.0)
    monkeypatch.setattr(services_test_account, "parse_test_account_benchmark", lambda: "QQQ")

    row = services_test_account.ensure_test_account(conn)
    assert row.name == TEST_ACCOUNT_NAME

    row = conn.execute(
        "SELECT name, account_kind, initial_cash, benchmark_ticker FROM accounts WHERE name = ?",
        (TEST_ACCOUNT_NAME,),
    ).fetchone()
    assert row is not None
    assert row["name"] == TEST_ACCOUNT_NAME
    assert row["account_kind"] == "manual_only"
    assert float(row["initial_cash"]) == 1.0
    assert row["benchmark_ticker"] == "QQQ"


def test_build_test_account_live_summary_uses_db_backed_shadow_account(conn, monkeypatch) -> None:
    monkeypatch.setattr(services_test_account, "compute_test_account_equity", lambda _rows=None: 1500.0)
    monkeypatch.setattr(services_test_account, "parse_test_account_benchmark", lambda: "QQQ")

    summary = services_test_account.build_test_account_live_summary(conn)

    assert summary["name"] == TEST_ACCOUNT_NAME
    assert summary["displayName"] == TEST_ACCOUNT_DISPLAY_NAME
    assert summary["benchmark"] == "QQQ"
    assert summary["equity"] == 1500.0


def test_ensure_test_account_returns_canonical_name(conn, monkeypatch) -> None:
    monkeypatch.setattr(services_test_account, "compute_test_account_equity", lambda _rows=None: 1000.0)
    monkeypatch.setattr(services_test_account, "parse_test_account_benchmark", lambda: "SPY")

    row = services_test_account.ensure_test_account(conn)
    assert row.name == TEST_ACCOUNT_NAME
