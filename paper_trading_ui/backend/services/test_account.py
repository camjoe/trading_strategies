from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from trading.models import AccountConfig, AccountRecord
from trading.services.accounts import (
    ACCOUNT_KIND_MANUAL_ONLY,
    ACCOUNT_KIND_TEST_SHADOW,
    configure_account,
    create_account,
    find_account,
    is_manual_only_account_kind,
    list_account_records,
)

from ..config import (
    TEST_ACCOUNT_BENCHMARK_DEFAULT,
    TEST_ACCOUNT_DISPLAY_NAME,
    TEST_ACCOUNT_NAME,
    TEST_BACKTEST_ACCOUNT_NAME,
    TEST_INVESTMENTS_CANDIDATES,
)
from ..schemas import TestInvestmentRow

MANUAL_ACCOUNT_SEARCH_KINDS = (ACCOUNT_KIND_MANUAL_ONLY, ACCOUNT_KIND_TEST_SHADOW)


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


def _normalize_account_name(account_name: str) -> str:
    name = account_name.strip()
    if not name:
        raise ValueError("account_name cannot be empty.")
    return name


def _select_manual_account_row(rows: list[AccountRecord]) -> AccountRecord | None:
    if not rows:
        return None

    preferred = next((row for row in rows if row.name == TEST_BACKTEST_ACCOUNT_NAME), None)
    if preferred is not None:
        return preferred

    if len(rows) > 1:
        names = ", ".join(sorted(row.name for row in rows))
        raise ValueError(f"Multiple manual-only accounts found: {names}")

    return rows[0]


def _ensure_manual_account_kind(conn: sqlite3.Connection, row: AccountRecord) -> AccountRecord:
    if is_manual_only_account_kind(row.account_kind):
        return row

    configure_account(
        conn,
        row.name,
        AccountConfig(account_kind=ACCOUNT_KIND_MANUAL_ONLY),
    )
    refreshed = find_account(conn, row.name)
    if refreshed is None:
        raise ValueError(f"Manual account '{row.name}' disappeared during normalization.")
    return refreshed


def resolve_backtest_account_name(account_name: str) -> str:
    """Legacy compatibility helper for callers that only need alias-to-name mapping."""
    name = _normalize_account_name(account_name)
    if name == TEST_ACCOUNT_NAME:
        return TEST_BACKTEST_ACCOUNT_NAME
    return name


def ensure_test_backtest_account(conn: sqlite3.Connection) -> AccountRecord:
    """Ensure one canonical manual-only account exists and return its DB row."""
    existing_by_legacy_name = find_account(conn, TEST_BACKTEST_ACCOUNT_NAME)
    if existing_by_legacy_name is not None:
        return _ensure_manual_account_kind(conn, existing_by_legacy_name)

    rows = list_account_records(conn, account_kinds=MANUAL_ACCOUNT_SEARCH_KINDS)
    selected = _select_manual_account_row(rows)
    if selected is not None:
        return _ensure_manual_account_kind(conn, selected)

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
            account_kind=ACCOUNT_KIND_MANUAL_ONLY,
            descriptive_name="TEST Account",
            risk_policy="none",
            instrument_mode="equity",
        ),
    )
    conn.commit()

    created = find_account(conn, TEST_BACKTEST_ACCOUNT_NAME)
    if created is None:
        raise ValueError("Failed to create canonical manual-only test account.")
    return created


def resolve_backtest_payload_account(account_name: str, conn: sqlite3.Connection) -> str:
    requested_name = _normalize_account_name(account_name)
    manual_account = ensure_test_backtest_account(conn)
    if requested_name in {TEST_ACCOUNT_NAME, manual_account.name}:
        return manual_account.name
    return requested_name


def is_manual_trade_account_name(account_name: str, conn: sqlite3.Connection) -> bool:
    requested_name = _normalize_account_name(account_name)
    manual_account = ensure_test_backtest_account(conn)
    return requested_name in {TEST_ACCOUNT_NAME, manual_account.name}


from .accounts import build_account_summary, require_account_row


def fetch_resolved_account_row(conn: sqlite3.Connection, account_name: str) -> AccountRecord:
    """Resolve ``account_name`` (handles test-account aliasing) and return its DB row."""
    resolved_name = resolve_backtest_payload_account(account_name, conn)
    return require_account_row(conn, resolved_name)


def build_test_account_live_summary(conn: sqlite3.Connection) -> dict[str, object]:
    """Build the canonical manual-account summary surfaced under external alias."""
    row = fetch_resolved_account_row(conn, TEST_ACCOUNT_NAME)
    summary = build_account_summary(conn, row)
    summary["name"] = TEST_ACCOUNT_NAME
    summary["displayName"] = TEST_ACCOUNT_DISPLAY_NAME
    return summary
