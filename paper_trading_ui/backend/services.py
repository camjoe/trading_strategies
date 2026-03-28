from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from fastapi import HTTPException

from trading.accounts import create_account
from trading.backtesting.backtest import (
    BacktestConfig,
    WalkForwardConfig,
    backtest_report_summary,
)
from trading.database.db import ensure_db
from trading.reporting import build_account_stats

from .config import (
    EXPORTS_DIR,
    TEST_ACCOUNT_BENCHMARK_DEFAULT,
    TEST_ACCOUNT_DISPLAY_NAME,
    TEST_ACCOUNT_NAME,
    TEST_ACCOUNT_STRATEGY,
    TEST_ACCOUNT_TRADE_TIME,
    TEST_BACKTEST_ACCOUNT_NAME,
    TEST_INVESTMENTS_CANDIDATES,
)
from .schemas import BacktestPreflightRequest, BacktestRunRequest, TestInvestmentRow, WalkForwardRunRequest


@contextmanager
def db_conn() -> Iterator[sqlite3.Connection]:
    conn = ensure_db()
    try:
        yield conn
    finally:
        conn.close()


def get_account_row(conn: sqlite3.Connection, account_name: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM accounts WHERE name = ?", (account_name,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Account '{account_name}' not found.")
    return row


def get_latest_snapshot_row(conn: sqlite3.Connection, account_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT snapshot_time, equity
        FROM equity_snapshots
        WHERE account_id = ?
        ORDER BY snapshot_time DESC, id DESC
        LIMIT 1
        """,
        (account_id,),
    ).fetchone()


def build_account_summary(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, object]:
    _state, _prices, _mv, _unrealized, equity = build_account_stats(conn, row)
    latest_snapshot = get_latest_snapshot_row(conn, int(row["id"]))

    initial_cash = float(row["initial_cash"])
    delta = equity - initial_cash
    delta_pct = ((equity / initial_cash) - 1.0) * 100.0 if initial_cash else 0.0

    change_since_snapshot = None
    if latest_snapshot is not None:
        previous_equity = float(latest_snapshot["equity"])
        change_since_snapshot = equity - previous_equity

    return {
        "name": row["name"],
        "displayName": row["descriptive_name"],
        "strategy": row["strategy"],
        "instrumentMode": row["instrument_mode"],
        "riskPolicy": row["risk_policy"],
        "benchmark": row["benchmark_ticker"],
        "initialCash": initial_cash,
        "equity": equity,
        "totalChange": delta,
        "totalChangePct": delta_pct,
        "changeSinceLastSnapshot": change_since_snapshot,
        "latestSnapshotTime": latest_snapshot["snapshot_time"] if latest_snapshot else None,
    }


def get_latest_backtest_summary(conn: sqlite3.Connection, account_name: str) -> dict[str, object] | None:
    row = conn.execute(
        """
        SELECT r.id, r.run_name, r.start_date, r.end_date, r.created_at, r.slippage_bps, r.fee_per_trade,
               r.tickers_file, a.name AS account_name, a.strategy
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        WHERE a.name = ?
        ORDER BY r.id DESC
        LIMIT 1
        """,
        (account_name,),
    ).fetchone()
    if row is None:
        return None
    return build_backtest_run_summary(row)


def build_backtest_run_summary(row: sqlite3.Row) -> dict[str, object]:
    account_name = str(row["account_name"])
    account_display_name = display_account_name(account_name)
    strategy_display_name = display_strategy(account_name, str(row["strategy"]))

    return {
        "runId": int(row["id"]),
        "runName": row["run_name"],
        "accountName": account_display_name,
        "strategy": strategy_display_name,
        "startDate": row["start_date"],
        "endDate": row["end_date"],
        "createdAt": row["created_at"],
        "slippageBps": float(row["slippage_bps"]),
        "feePerTrade": float(row["fee_per_trade"]),
        "tickersFile": row["tickers_file"],
    }


def display_account_name(account_name: str) -> str:
    return TEST_ACCOUNT_NAME if account_name == TEST_BACKTEST_ACCOUNT_NAME else account_name


def display_strategy(account_name: str, strategy: str) -> str:
    return TEST_ACCOUNT_STRATEGY if account_name == TEST_BACKTEST_ACCOUNT_NAME else strategy


def get_managed_account_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM accounts WHERE name != ? ORDER BY name",
        (TEST_BACKTEST_ACCOUNT_NAME,),
    ).fetchall()


def build_comparison_account_payload(
    summary: dict[str, object],
    latest_backtest: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "name": summary["name"],
        "displayName": summary["displayName"],
        "strategy": summary["strategy"],
        "benchmark": summary["benchmark"],
        "equity": summary["equity"],
        "initialCash": summary["initialCash"],
        "totalChange": summary["totalChange"],
        "totalChangePct": summary["totalChangePct"],
        "latestBacktest": latest_backtest,
    }


def build_snapshot_payload(snapshot: sqlite3.Row) -> dict[str, object]:
    return {
        "time": snapshot["snapshot_time"],
        "cash": float(snapshot["cash"]),
        "marketValue": float(snapshot["market_value"]),
        "equity": float(snapshot["equity"]),
        "realizedPnl": float(snapshot["realized_pnl"]),
        "unrealizedPnl": float(snapshot["unrealized_pnl"]),
    }


def build_trade_payload(trade: sqlite3.Row) -> dict[str, object]:
    return {
        "ticker": trade["ticker"],
        "side": trade["side"],
        "qty": float(trade["qty"]),
        "price": float(trade["price"]),
        "fee": float(trade["fee"]),
        "tradeTime": trade["trade_time"],
    }


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def build_rotation_schedule_json(value: list[str] | None) -> str | None:
    if not value:
        return None
    normalized = [item.strip() for item in value if item and item.strip()]
    if not normalized:
        return None
    unique: list[str] = []
    for item in normalized:
        if item not in unique:
            unique.append(item)
    return json.dumps(unique, separators=(",", ":"))


def delete_account_and_dependents(conn: sqlite3.Connection, account_name: str) -> dict[str, int]:
    account = conn.execute("SELECT id FROM accounts WHERE name = ?", (account_name,)).fetchone()
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account '{account_name}' not found.")

    account_id = int(account["id"])
    run_rows = conn.execute("SELECT id FROM backtest_runs WHERE account_id = ?", (account_id,)).fetchall()
    run_ids = tuple(int(row["id"]) for row in run_rows)

    counts = {
        "accounts": 1,
        "trades": int(conn.execute("SELECT COUNT(*) AS n FROM trades WHERE account_id = ?", (account_id,)).fetchone()["n"]),
        "equitySnapshots": int(
            conn.execute("SELECT COUNT(*) AS n FROM equity_snapshots WHERE account_id = ?", (account_id,)).fetchone()["n"]
        ),
        "backtestRuns": len(run_ids),
        "backtestTrades": 0,
        "backtestEquitySnapshots": 0,
    }

    conn.execute("BEGIN")
    if run_ids:
        placeholders = ",".join(["?"] * len(run_ids))
        counts["backtestTrades"] = int(
            conn.execute(
                f"SELECT COUNT(*) AS n FROM backtest_trades WHERE run_id IN ({placeholders})",
                run_ids,
            ).fetchone()["n"]
        )
        counts["backtestEquitySnapshots"] = int(
            conn.execute(
                f"SELECT COUNT(*) AS n FROM backtest_equity_snapshots WHERE run_id IN ({placeholders})",
                run_ids,
            ).fetchone()["n"]
        )
        conn.execute(f"DELETE FROM backtest_equity_snapshots WHERE run_id IN ({placeholders})", run_ids)
        conn.execute(f"DELETE FROM backtest_trades WHERE run_id IN ({placeholders})", run_ids)
        conn.execute(f"DELETE FROM backtest_runs WHERE id IN ({placeholders})", run_ids)

    conn.execute("DELETE FROM equity_snapshots WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM trades WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    conn.commit()
    return counts


def get_latest_backtest_metrics(conn: sqlite3.Connection, account_name: str) -> dict[str, object] | None:
    latest_row = conn.execute(
        """
        SELECT r.id
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        WHERE a.name = ?
        ORDER BY r.id DESC
        LIMIT 1
        """,
        (account_name,),
    ).fetchone()
    if latest_row is None:
        return None

    report = backtest_report_summary(conn, int(latest_row["id"]))
    return {
        "runId": report.run_id,
        "endDate": report.end_date,
        "totalReturnPct": report.total_return_pct,
        "maxDrawdownPct": report.max_drawdown_pct,
        "alphaPct": None,
    }


def build_backtest_config_from_run_request(payload: BacktestRunRequest) -> BacktestConfig:
    return BacktestConfig(
        account_name=payload.account,
        tickers_file=payload.tickersFile,
        universe_history_dir=payload.universeHistoryDir,
        start=payload.start,
        end=payload.end,
        lookback_months=payload.lookbackMonths,
        slippage_bps=payload.slippageBps,
        fee_per_trade=payload.fee,
        run_name=payload.runName,
        allow_approximate_leaps=payload.allowApproximateLeaps,
    )


def build_backtest_config_from_preflight_request(payload: BacktestPreflightRequest) -> BacktestConfig:
    return BacktestConfig(
        account_name=payload.account,
        tickers_file=payload.tickersFile,
        universe_history_dir=payload.universeHistoryDir,
        start=payload.start,
        end=payload.end,
        lookback_months=payload.lookbackMonths,
        slippage_bps=0.0,
        fee_per_trade=0.0,
        run_name=None,
        allow_approximate_leaps=payload.allowApproximateLeaps,
    )


def build_walk_forward_config_from_request(payload: WalkForwardRunRequest) -> WalkForwardConfig:
    return WalkForwardConfig(
        account_name=payload.account,
        tickers_file=payload.tickersFile,
        universe_history_dir=payload.universeHistoryDir,
        start=payload.start,
        end=payload.end,
        lookback_months=payload.lookbackMonths,
        test_months=payload.testMonths,
        step_months=payload.stepMonths,
        slippage_bps=payload.slippageBps,
        fee_per_trade=payload.fee,
        run_name_prefix=payload.runNamePrefix,
        allow_approximate_leaps=payload.allowApproximateLeaps,
    )


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


def resolve_csv_export_file(export_name: str, file_name: str) -> Path:
    base = EXPORTS_DIR.resolve()
    candidate = (base / export_name / file_name).resolve()

    if os.path.commonpath([str(base), str(candidate)]) != str(base):
        raise HTTPException(status_code=400, detail="Invalid export path")
    if candidate.suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    return candidate


def resolve_backtest_account_name(account_name: str) -> str:
    name = account_name.strip()
    if name == TEST_ACCOUNT_NAME:
        return TEST_BACKTEST_ACCOUNT_NAME
    return name


def ensure_test_backtest_account(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT id FROM accounts WHERE name = ?", (TEST_BACKTEST_ACCOUNT_NAME,)).fetchone()
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
        descriptive_name="TEST Account (Backtest Shadow)",
        risk_policy="none",
        instrument_mode="equity",
    )
    conn.commit()


def resolve_backtest_payload_account(account_name: str, conn: sqlite3.Connection) -> str:
    resolved = resolve_backtest_account_name(account_name)
    if resolved == TEST_BACKTEST_ACCOUNT_NAME:
        ensure_test_backtest_account(conn)
    return resolved


def list_csv_exports() -> dict[str, object]:
    if not EXPORTS_DIR.exists():
        return {"exports": []}

    export_dirs = sorted(
        [path for path in EXPORTS_DIR.iterdir() if path.is_dir() and path.name.startswith("db_csv_")],
        key=lambda path: path.name,
        reverse=True,
    )

    exports: list[dict[str, object]] = []
    for export_dir in export_dirs:
        csv_files = sorted(export_dir.glob("*.csv"), key=lambda path: path.name)
        files = [{"name": csv_file.name, "sizeBytes": int(csv_file.stat().st_size)} for csv_file in csv_files]
        exports.append(
            {
                "name": export_dir.name,
                "modifiedAt": datetime.fromtimestamp(export_dir.stat().st_mtime).isoformat(timespec="seconds"),
                "files": files,
            }
        )

    return {"exports": exports}


def preview_csv_export(export_name: str, file_name: str, limit: int) -> dict[str, object]:
    path = resolve_csv_export_file(export_name, file_name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="CSV file not found")

    with path.open("r", encoding="utf-8", errors="replace", newline="") as file_handle:
        reader = csv.reader(file_handle)
        header = next(reader, [])
        rows: list[list[str]] = []
        for _ in range(limit):
            try:
                rows.append([str(cell) for cell in next(reader)])
            except StopIteration:
                break

        truncated = False
        try:
            next(reader)
            truncated = True
        except StopIteration:
            truncated = False

    return {
        "exportName": export_name,
        "fileName": file_name,
        "header": [str(col) for col in header],
        "rows": rows,
        "returned": len(rows),
        "truncated": truncated,
    }

