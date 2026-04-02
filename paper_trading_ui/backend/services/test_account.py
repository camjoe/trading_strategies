from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from trading.services.accounts_service import create_account
from trading.models import AccountConfig
from trading.services.accounts_service import fetch_account_by_name

from ..config import (
    TEST_ACCOUNT_BENCHMARK_DEFAULT,
    TEST_ACCOUNT_DISPLAY_NAME,
    TEST_ACCOUNT_NAME,
    TEST_ACCOUNT_STRATEGY,
    TEST_ACCOUNT_TRADE_TIME,
    TEST_BACKTEST_ACCOUNT_NAME,
    TEST_INVESTMENTS_CANDIDATES,
)
from ..schemas import TestInvestmentRow


def get_test_investments_path() -> Path | None:
    for candidate in TEST_INVESTMENTS_CANDIDATES:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def parse_test_investments() -> list[TestInvestmentRow]:
    """Parse checked rows from local test investments file.

    Expected row format examples:
    - [x] TICKER ($1500 - note)
    - [ ] TICKER
    """
    path = get_test_investments_path()
    if path is None:
        return []

    line_re = re.compile(r"^\s*-\s*\[(?P<flag>[xX ])\]\s*(?P<ticker>[A-Za-z0-9._-]+)(?:\s*\((?P<meta>[^)]*)\))?")
    amount_re = re.compile(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)")

    results: list[TestInvestmentRow] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = line_re.match(raw_line)
        if not match:
            continue

        flag = match.group("flag")
        if flag.lower() != "x":
            continue

        ticker = (match.group("ticker") or "").strip().upper()
        if not ticker:
            continue

        meta = match.group("meta") or ""
        amount_match = amount_re.search(meta)
        amount = 0.0
        if amount_match:
            amount_raw = amount_match.group(1).replace(",", "")
            try:
                amount = float(amount_raw)
            except ValueError:
                amount = 0.0

        results.append({"ticker": ticker, "amount": amount})

    return results


def compute_test_account_equity(rows: list[TestInvestmentRow] | None = None) -> float:
    investments = rows if rows is not None else parse_test_investments()
    return sum(item["amount"] for item in investments)


def parse_test_account_benchmark() -> str:
    """Read benchmark override from the same test investments file.

    Supported line formats (case-insensitive):
      benchmark: QQQ
      benchmark = SPY
      test_benchmark: VTI
    """
    path = get_test_investments_path()
    if path is None:
        return TEST_ACCOUNT_BENCHMARK_DEFAULT

    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?im)^\s*(?:benchmark|test_benchmark)\s*[:=]\s*([A-Za-z0-9._-]+)\s*$", text)
    if not match:
        return TEST_ACCOUNT_BENCHMARK_DEFAULT

    return str(match.group(1)).strip().upper() or TEST_ACCOUNT_BENCHMARK_DEFAULT


def build_test_account_summary() -> dict[str, object]:
    rows = parse_test_investments()
    equity = compute_test_account_equity(rows)
    benchmark = parse_test_account_benchmark()
    return {
        "name": TEST_ACCOUNT_NAME,
        "displayName": TEST_ACCOUNT_DISPLAY_NAME,
        "strategy": TEST_ACCOUNT_STRATEGY,
        "instrumentMode": "equity",
        "riskPolicy": "none",
        "benchmark": benchmark,
        "initialCash": equity,
        "equity": equity,
        "totalChange": 0.0,
        "totalChangePct": 0.0,
        "changeSinceLastSnapshot": 0.0,
        "latestSnapshotTime": TEST_ACCOUNT_TRADE_TIME,
    }


def build_test_account_detail_payload() -> dict[str, object]:
    rows = parse_test_investments()
    equity = compute_test_account_equity(rows)
    trades = [
        {
            "ticker": item["ticker"],
            "side": "buy",
            "qty": 1.0,
            "price": item["amount"],
            "fee": 0.0,
            "tradeTime": TEST_ACCOUNT_TRADE_TIME,
        }
        for item in rows
    ]

    snapshots = [
        {
            "time": TEST_ACCOUNT_TRADE_TIME,
            "cash": 0.0,
            "marketValue": equity,
            "equity": equity,
            "realizedPnl": 0.0,
            "unrealizedPnl": 0.0,
        }
    ]

    return {
        "account": build_test_account_summary(),
        "latestBacktest": None,
        "snapshots": snapshots,
        "trades": trades,
    }


def resolve_backtest_account_name(account_name: str) -> str:
    name = account_name.strip()
    if name == TEST_ACCOUNT_NAME:
        return TEST_BACKTEST_ACCOUNT_NAME
    return name


def ensure_test_backtest_account(conn: sqlite3.Connection) -> None:
    existing = fetch_account_by_name(conn, TEST_BACKTEST_ACCOUNT_NAME)
    if existing is not None:
        return

    initial_cash = compute_test_account_equity()
    if initial_cash <= 0:
        initial_cash = 1.0

    create_account(
        conn,
        name=TEST_BACKTEST_ACCOUNT_NAME,
        strategy="trend",
        initial_cash=initial_cash,
        benchmark_ticker=parse_test_account_benchmark(),
        config=AccountConfig(
            descriptive_name="TEST Account (Backtest Shadow)",
            risk_policy="none",
            instrument_mode="equity",
        ),
    )
    conn.commit()


def resolve_backtest_payload_account(account_name: str, conn: sqlite3.Connection) -> str:
    resolved = resolve_backtest_account_name(account_name)
    if resolved == TEST_BACKTEST_ACCOUNT_NAME:
        ensure_test_backtest_account(conn)
    return resolved
