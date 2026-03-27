from __future__ import annotations

import os
import csv
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, TypedDict

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from trading.accounts import create_account
from trading.accounting import load_trades
from trading.backtesting.backtest import (
    BacktestConfig,
    backtest_report,
    preview_backtest_warnings,
    run_backtest,
    WalkForwardConfig,
    run_walk_forward_backtest,
)
from trading.database.db import ensure_db
from trading.database.db_backend import DuplicateRecordError
from trading.reporting import build_account_stats, snapshot_account
from common.repo_paths import get_repo_root

ROOT_DIR = get_repo_root(__file__)
BACKEND_DIR = Path(__file__).resolve().parent

load_dotenv(BACKEND_DIR / ".env")


def _parse_cors_origins(raw: str) -> list[str]:
    cleaned = [item.strip() for item in raw.split(",") if item.strip()]
    return cleaned or ["*"]


logs_dir_raw = os.getenv("LOGS_DIR", "local/logs")
LOGS_DIR = (ROOT_DIR / logs_dir_raw).resolve() if not Path(logs_dir_raw).is_absolute() else Path(logs_dir_raw).resolve()
EXPORTS_DIR = (ROOT_DIR / "local" / "exports").resolve()
TEST_INVESTMENTS_CANDIDATES = (
    (ROOT_DIR / "local" / "test_investments.txt").resolve(),
    (ROOT_DIR / "local" / "test_invesments.txt").resolve(),
)
TEST_ACCOUNT_NAME = "test_account"
TEST_BACKTEST_ACCOUNT_NAME = "test_account_bt"
TEST_ACCOUNT_DISPLAY_NAME = "TEST Account"
TEST_ACCOUNT_STRATEGY = "Manual Test Investments"
TEST_ACCOUNT_BENCHMARK_DEFAULT = "SPY"
TEST_ACCOUNT_TRADE_TIME = "2025-01-11T12:00:00Z"
cors_origins = _parse_cors_origins(os.getenv("CORS_ORIGINS", "*"))

app = FastAPI(title="Paper Trading UI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@contextmanager
def _db_conn() -> Iterator[sqlite3.Connection]:
    conn = ensure_db()
    try:
        yield conn
    finally:
        conn.close()


def _account_row(conn: sqlite3.Connection, account_name: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM accounts WHERE name = ?", (account_name,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Account '{account_name}' not found.")
    return row


def _snapshot_row(conn: sqlite3.Connection, account_id: int) -> sqlite3.Row | None:
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


def _build_account_summary(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, object]:
    _state, _prices, _mv, _unrealized, equity = build_account_stats(conn, row)
    latest_snapshot = _snapshot_row(conn, int(row["id"]))

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


def _latest_backtest_summary(conn: sqlite3.Connection, account_name: str) -> dict[str, object] | None:
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
    return _backtest_run_summary(row)


def _backtest_run_summary(row: sqlite3.Row) -> dict[str, object]:
    account_name = str(row["account_name"])
    display_account_name = _display_account_name(account_name)
    display_strategy = _display_strategy(account_name, str(row["strategy"]))

    return {
        "runId": int(row["id"]),
        "runName": row["run_name"],
        "accountName": display_account_name,
        "strategy": display_strategy,
        "startDate": row["start_date"],
        "endDate": row["end_date"],
        "createdAt": row["created_at"],
        "slippageBps": float(row["slippage_bps"]),
        "feePerTrade": float(row["fee_per_trade"]),
        "tickersFile": row["tickers_file"],
    }


def _display_account_name(account_name: str) -> str:
    return TEST_ACCOUNT_NAME if account_name == TEST_BACKTEST_ACCOUNT_NAME else account_name


def _display_strategy(account_name: str, strategy: str) -> str:
    return TEST_ACCOUNT_STRATEGY if account_name == TEST_BACKTEST_ACCOUNT_NAME else strategy


def _managed_account_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM accounts WHERE name != ? ORDER BY name",
        (TEST_BACKTEST_ACCOUNT_NAME,),
    ).fetchall()


def _comparison_account_payload(
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


def _snapshot_payload(snapshot: sqlite3.Row) -> dict[str, object]:
    return {
        "time": snapshot["snapshot_time"],
        "cash": float(snapshot["cash"]),
        "marketValue": float(snapshot["market_value"]),
        "equity": float(snapshot["equity"]),
        "realizedPnl": float(snapshot["realized_pnl"]),
        "unrealizedPnl": float(snapshot["unrealized_pnl"]),
    }


def _trade_payload(trade: sqlite3.Row) -> dict[str, object]:
    return {
        "ticker": trade["ticker"],
        "side": trade["side"],
        "qty": float(trade["qty"]),
        "price": float(trade["price"]),
        "fee": float(trade["fee"]),
        "tradeTime": trade["trade_time"],
    }


class BacktestRunRequest(BaseModel):
    account: str
    tickersFile: str = "trading/trade_universe.txt"
    universeHistoryDir: str | None = None
    start: str | None = None
    end: str | None = None
    lookbackMonths: int | None = Field(default=None, gt=0)
    slippageBps: float = 5.0
    fee: float = 0.0
    runName: str | None = None
    allowApproximateLeaps: bool = False


class WalkForwardRunRequest(BaseModel):
    account: str
    tickersFile: str = "trading/trade_universe.txt"
    universeHistoryDir: str | None = None
    start: str | None = None
    end: str | None = None
    lookbackMonths: int | None = Field(default=None, gt=0)
    testMonths: int = Field(default=1, gt=0)
    stepMonths: int = Field(default=1, gt=0)
    slippageBps: float = 5.0
    fee: float = 0.0
    runNamePrefix: str | None = None
    allowApproximateLeaps: bool = False


class BacktestPreflightRequest(BaseModel):
    account: str
    tickersFile: str = "trading/trade_universe.txt"
    universeHistoryDir: str | None = None
    start: str | None = None
    end: str | None = None
    lookbackMonths: int | None = Field(default=None, gt=0)
    allowApproximateLeaps: bool = False


class TestInvestmentRow(TypedDict):
    ticker: str
    amount: float


class AdminCreateAccountRequest(BaseModel):
    name: str
    strategy: str
    initialCash: float = Field(gt=0)
    benchmarkTicker: str = "SPY"
    descriptiveName: str | None = None
    goalMinReturnPct: float | None = None
    goalMaxReturnPct: float | None = None
    goalPeriod: str = "monthly"
    learningEnabled: bool = False
    riskPolicy: str = "none"
    stopLossPct: float | None = None
    takeProfitPct: float | None = None
    instrumentMode: str = "equity"
    optionStrikeOffsetPct: float | None = None
    optionMinDte: int | None = None
    optionMaxDte: int | None = None
    optionType: str | None = None
    targetDeltaMin: float | None = None
    targetDeltaMax: float | None = None
    maxPremiumPerTrade: float | None = None
    maxContractsPerTrade: int | None = None
    ivRankMin: float | None = None
    ivRankMax: float | None = None
    rollDteThreshold: int | None = None
    profitTakePct: float | None = None
    maxLossPct: float | None = None
    rotationEnabled: bool = False
    rotationMode: str = "time"
    rotationOptimalityMode: str = "previous_period_best"
    rotationIntervalDays: int | None = None
    rotationLookbackDays: int | None = None
    rotationSchedule: list[str] | None = None
    rotationActiveIndex: int = 0
    rotationLastAt: str | None = None
    rotationActiveStrategy: str | None = None


class AdminDeleteAccountRequest(BaseModel):
    accountName: str
    confirm: bool = False


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _rotation_schedule_json(value: list[str] | None) -> str | None:
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


def _delete_account_and_dependents(conn: sqlite3.Connection, account_name: str) -> dict[str, int]:
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


def _latest_backtest_metrics(conn: sqlite3.Connection, account_name: str) -> dict[str, object] | None:
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

    report = backtest_report(conn, int(latest_row["id"]))
    return {
        "runId": int(report["run_id"]),
        "endDate": report["end_date"],
        "totalReturnPct": float(report["total_return_pct"]),
        "maxDrawdownPct": float(report["max_drawdown_pct"]),
        "alphaPct": float(report["alpha_pct"]) if report.get("alpha_pct") is not None else None,
    }


def _backtest_config_from_run_request(payload: BacktestRunRequest) -> BacktestConfig:
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


def _backtest_config_from_preflight_request(payload: BacktestPreflightRequest) -> BacktestConfig:
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


def _walk_forward_config_from_request(payload: WalkForwardRunRequest) -> WalkForwardConfig:
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


def _test_investments_path() -> Path | None:
    for candidate in TEST_INVESTMENTS_CANDIDATES:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _parse_test_investments() -> list[TestInvestmentRow]:
    """Parse checked rows from local test investments file.

    Expected row format examples:
    - [x] TICKER ($1500 - note)
    - [ ] TICKER
    """
    path = _test_investments_path()
    if path is None:
        return []

    line_re = re.compile(r"^\s*-\s*\[(?P<flag>[xX ])\]\s*(?P<ticker>[A-Za-z0-9._-]+)(?:\s*\((?P<meta>[^)]*)\))?")
    amount_re = re.compile(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)")

    results: list[TestInvestmentRow] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = line_re.match(raw_line)
        if not m:
            continue

        flag = m.group("flag")
        if flag.lower() != "x":
            continue

        ticker = (m.group("ticker") or "").strip().upper()
        if not ticker:
            continue

        meta = m.group("meta") or ""
        amount_match = amount_re.search(meta)
        amount = 0.0
        if amount_match:
            amount_raw = amount_match.group(1).replace(",", "")
            try:
                amount = float(amount_raw)
            except ValueError:
                amount = 0.0

        results.append(
            {
                "ticker": ticker,
                "amount": amount,
            }
        )

    return results


def _test_account_equity(rows: list[TestInvestmentRow] | None = None) -> float:
    investments = rows if rows is not None else _parse_test_investments()
    return sum(item["amount"] for item in investments)


def _parse_test_account_benchmark() -> str:
    """Read benchmark override from the same test investments file.

    Supported line formats (case-insensitive):
      benchmark: QQQ
      benchmark = SPY
      test_benchmark: VTI
    """
    path = _test_investments_path()
    if path is None:
        return TEST_ACCOUNT_BENCHMARK_DEFAULT

    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?im)^\s*(?:benchmark|test_benchmark)\s*[:=]\s*([A-Za-z0-9._-]+)\s*$", text)
    if not match:
        return TEST_ACCOUNT_BENCHMARK_DEFAULT

    return str(match.group(1)).strip().upper() or TEST_ACCOUNT_BENCHMARK_DEFAULT


def _test_account_summary() -> dict[str, object]:
    rows = _parse_test_investments()
    equity = _test_account_equity(rows)
    benchmark = _parse_test_account_benchmark()
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


def _test_account_detail_payload() -> dict[str, object]:
    rows = _parse_test_investments()
    equity = _test_account_equity(rows)
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
        "account": _test_account_summary(),
        "latestBacktest": None,
        "snapshots": snapshots,
        "trades": trades,
    }


def _resolve_csv_export_file(export_name: str, file_name: str) -> Path:
    base = EXPORTS_DIR.resolve()
    candidate = (base / export_name / file_name).resolve()

    if os.path.commonpath([str(base), str(candidate)]) != str(base):
        raise HTTPException(status_code=400, detail="Invalid export path")
    if candidate.suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    return candidate


def _resolve_backtest_account_name(account_name: str) -> str:
    name = account_name.strip()
    if name == TEST_ACCOUNT_NAME:
        return TEST_BACKTEST_ACCOUNT_NAME
    return name


def _ensure_test_backtest_account(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT id FROM accounts WHERE name = ?", (TEST_BACKTEST_ACCOUNT_NAME,)).fetchone()
    if existing is not None:
        return

    initial_cash = _test_account_equity()
    if initial_cash <= 0:
        initial_cash = 1.0

    create_account(
        conn,
        name=TEST_BACKTEST_ACCOUNT_NAME,
        strategy="trend",
        initial_cash=initial_cash,
        benchmark_ticker=_parse_test_account_benchmark(),
        descriptive_name="TEST Account (Backtest Shadow)",
        risk_policy="none",
        instrument_mode="equity",
    )
    conn.commit()


def _resolve_backtest_payload_account(account_name: str, conn: sqlite3.Connection) -> str:
    resolved = _resolve_backtest_account_name(account_name)
    if resolved == TEST_BACKTEST_ACCOUNT_NAME:
        _ensure_test_backtest_account(conn)
    return resolved


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/accounts")
def api_accounts() -> dict[str, list[dict[str, object]]]:
    with _db_conn() as conn:
        rows = _managed_account_rows(conn)
        accounts = [_build_account_summary(conn, r) for r in rows]
        accounts.append(_test_account_summary())
        accounts.sort(key=lambda item: str(item["name"]))
        return {"accounts": accounts}


@app.get("/api/accounts/compare")
def api_accounts_compare() -> dict[str, list[dict[str, object]]]:
    with _db_conn() as conn:
        rows = _managed_account_rows(conn)
        comparison: list[dict[str, object]] = []
        for row in rows:
            summary = _build_account_summary(conn, row)
            latest_backtest = _latest_backtest_metrics(conn, str(row["name"]))
            comparison.append(_comparison_account_payload(summary, latest_backtest))

        test_summary = _test_account_summary()
        comparison.append(_comparison_account_payload(test_summary, None))
        comparison.sort(key=lambda item: str(item["name"]))
        return {"accounts": comparison}


@app.get("/api/accounts/{account_name}")
def api_account_detail(account_name: str) -> dict[str, object]:
    if account_name == TEST_ACCOUNT_NAME:
        payload = _test_account_detail_payload()
        with _db_conn() as conn:
            resolved_account_name = _resolve_backtest_payload_account(account_name, conn)
            payload["latestBacktest"] = _latest_backtest_summary(conn, resolved_account_name)
        return payload

    with _db_conn() as conn:
        account = _account_row(conn, account_name)
        summary = _build_account_summary(conn, account)

        snapshots = conn.execute(
            """
            SELECT snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
            FROM equity_snapshots
            WHERE account_id = ?
            ORDER BY snapshot_time DESC, id DESC
            LIMIT 100
            """,
            (int(account["id"]),),
        ).fetchall()

        trades = load_trades(conn, int(account["id"]))
        latest_backtest = _latest_backtest_summary(conn, account_name)

        return {
            "account": summary,
            "latestBacktest": latest_backtest,
            "snapshots": [_snapshot_payload(s) for s in snapshots],
            "trades": [_trade_payload(t) for t in trades[-100:]],
        }


@app.post("/api/admin/accounts/create")
def api_admin_create_account(payload: AdminCreateAccountRequest) -> dict[str, object]:
    with _db_conn() as conn:
        try:
            create_account(
                conn,
                name=payload.name.strip(),
                strategy=payload.strategy.strip(),
                initial_cash=float(payload.initialCash),
                benchmark_ticker=payload.benchmarkTicker.strip().upper(),
                descriptive_name=_clean_text(payload.descriptiveName),
                goal_min_return_pct=payload.goalMinReturnPct,
                goal_max_return_pct=payload.goalMaxReturnPct,
                goal_period=payload.goalPeriod,
                learning_enabled=bool(payload.learningEnabled),
                risk_policy=payload.riskPolicy,
                stop_loss_pct=payload.stopLossPct,
                take_profit_pct=payload.takeProfitPct,
                instrument_mode=payload.instrumentMode,
                option_strike_offset_pct=payload.optionStrikeOffsetPct,
                option_min_dte=payload.optionMinDte,
                option_max_dte=payload.optionMaxDte,
                option_type=_clean_text(payload.optionType),
                target_delta_min=payload.targetDeltaMin,
                target_delta_max=payload.targetDeltaMax,
                max_premium_per_trade=payload.maxPremiumPerTrade,
                max_contracts_per_trade=payload.maxContractsPerTrade,
                iv_rank_min=payload.ivRankMin,
                iv_rank_max=payload.ivRankMax,
                roll_dte_threshold=payload.rollDteThreshold,
                profit_take_pct=payload.profitTakePct,
                max_loss_pct=payload.maxLossPct,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except DuplicateRecordError as error:
            raise HTTPException(status_code=400, detail=f"Account create failed: {error}") from error

        rotation_schedule = _rotation_schedule_json(payload.rotationSchedule)
        conn.execute(
            """
            UPDATE accounts
            SET rotation_enabled = ?,
                rotation_mode = ?,
                rotation_optimality_mode = ?,
                rotation_interval_days = ?,
                rotation_lookback_days = ?,
                rotation_schedule = ?,
                rotation_active_index = ?,
                rotation_last_at = ?,
                rotation_active_strategy = ?
            WHERE name = ?
            """,
            (
                1 if payload.rotationEnabled else 0,
                payload.rotationMode.strip().lower(),
                payload.rotationOptimalityMode.strip().lower(),
                payload.rotationIntervalDays,
                payload.rotationLookbackDays,
                rotation_schedule,
                int(payload.rotationActiveIndex),
                _clean_text(payload.rotationLastAt),
                _clean_text(payload.rotationActiveStrategy),
                payload.name.strip(),
            ),
        )
        conn.commit()

        account = _account_row(conn, payload.name.strip())
        return {
            "status": "ok",
            "account": _build_account_summary(conn, account),
        }


@app.post("/api/admin/accounts/delete")
def api_admin_delete_account(payload: AdminDeleteAccountRequest) -> dict[str, object]:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Deletion requires explicit confirmation.")

    if payload.accountName.strip() == TEST_ACCOUNT_NAME:
        raise HTTPException(status_code=400, detail="TEST Account is virtual and cannot be deleted.")

    with _db_conn() as conn:
        counts = _delete_account_and_dependents(conn, payload.accountName.strip())
        return {
            "status": "ok",
            "deleted": counts,
        }


@app.get("/api/admin/exports/csv")
def api_csv_exports() -> dict[str, object]:
    if not EXPORTS_DIR.exists():
        return {"exports": []}

    export_dirs = sorted(
        [p for p in EXPORTS_DIR.iterdir() if p.is_dir() and p.name.startswith("db_csv_")],
        key=lambda p: p.name,
        reverse=True,
    )

    exports: list[dict[str, object]] = []
    for export_dir in export_dirs:
        csv_files = sorted(export_dir.glob("*.csv"), key=lambda p: p.name)
        files = [
            {
                "name": csv_file.name,
                "sizeBytes": int(csv_file.stat().st_size),
            }
            for csv_file in csv_files
        ]
        exports.append(
            {
                "name": export_dir.name,
                "modifiedAt": datetime.fromtimestamp(export_dir.stat().st_mtime).isoformat(timespec="seconds"),
                "files": files,
            }
        )

    return {"exports": exports}


@app.get("/api/admin/exports/csv/preview")
def api_csv_export_preview(
    exportName: str = Query(..., min_length=1),
    fileName: str = Query(..., min_length=1),
    limit: int = Query(default=200, ge=1, le=2000),
) -> dict[str, object]:
    path = _resolve_csv_export_file(exportName, fileName)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="CSV file not found")

    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.reader(fh)
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
        "exportName": exportName,
        "fileName": fileName,
        "header": [str(col) for col in header],
        "rows": rows,
        "returned": len(rows),
        "truncated": truncated,
    }


@app.get("/api/logs/files")
def api_log_files() -> dict[str, list[str]]:
    if not LOGS_DIR.exists():
        return {"files": []}
    files = sorted([p.name for p in LOGS_DIR.glob("*.log")], reverse=True)
    return {"files": files}


@app.get("/api/logs/{file_name}")
def api_log_file(
    file_name: str,
    limit: int = Query(default=400, ge=10, le=4000),
    contains: str | None = Query(default=None),
) -> dict[str, object]:
    path = (LOGS_DIR / file_name).resolve()
    if not str(path).startswith(str(LOGS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid log path")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if contains:
        needle = contains.lower().strip()
        lines = [line for line in lines if needle in line.lower()]

    sliced = lines[-limit:]
    return {
        "file": file_name,
        "lineCount": len(lines),
        "returned": len(sliced),
        "lines": sliced,
    }


@app.post("/api/actions/snapshot/{account_name}")
def api_snapshot(account_name: str) -> dict[str, str]:
    if account_name == TEST_ACCOUNT_NAME:
        return {"status": "ok", "message": "TEST Account snapshot is virtual."}

    with _db_conn() as conn:
        _account_row(conn, account_name)
        snapshot_account(conn, account_name, snapshot_time=None)
        return {"status": "ok", "message": f"Snapshot saved for {account_name}"}


@app.post("/api/actions/snapshot-all")
def api_snapshot_all() -> dict[str, object]:
    with _db_conn() as conn:
        rows = conn.execute("SELECT name FROM accounts ORDER BY name").fetchall()
        names = [str(r["name"]) for r in rows]
        for name in names:
            snapshot_account(conn, name, snapshot_time=None)
        return {"status": "ok", "snapshotted": names + [TEST_ACCOUNT_NAME]}


@app.get("/api/backtests/runs")
def api_backtest_runs(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, list[dict[str, object]]]:
    with _db_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.run_name, r.start_date, r.end_date, r.created_at, r.slippage_bps, r.fee_per_trade,
                   r.tickers_file, a.name AS account_name, a.strategy
            FROM backtest_runs r
            JOIN accounts a ON a.id = r.account_id
            ORDER BY r.id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return {"runs": [_backtest_run_summary(r) for r in rows]}


@app.get("/api/backtests/latest/{account_name}")
def api_latest_backtest_for_account(account_name: str) -> dict[str, object]:
    with _db_conn() as conn:
        resolved_account_name = _resolve_backtest_payload_account(account_name, conn)
        _account_row(conn, resolved_account_name)
        latest = _latest_backtest_summary(conn, resolved_account_name)
        return {
            "accountName": account_name,
            "latestRun": latest,
        }


@app.get("/api/backtests/runs/{run_id}")
def api_backtest_run_report(run_id: int) -> dict[str, object]:
    with _db_conn() as conn:
        try:
            return backtest_report(conn, run_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/backtests/run")
def api_run_backtest(payload: BacktestRunRequest) -> dict[str, object]:
    with _db_conn() as conn:
        resolved_account_name = _resolve_backtest_payload_account(payload.account, conn)
        payload = payload.model_copy(update={"account": resolved_account_name})
        try:
            result = run_backtest(conn, _backtest_config_from_run_request(payload))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        display_account_name = _display_account_name(result.account_name)

        return {
            "runId": result.run_id,
            "accountName": display_account_name,
            "startDate": result.start_date,
            "endDate": result.end_date,
            "tradeCount": result.trade_count,
            "endingEquity": result.ending_equity,
            "totalReturnPct": result.total_return_pct,
            "benchmarkReturnPct": result.benchmark_return_pct,
            "alphaPct": result.alpha_pct,
            "maxDrawdownPct": result.max_drawdown_pct,
            "warnings": result.warnings,
        }


@app.post("/api/backtests/preflight")
def api_backtest_preflight(payload: BacktestPreflightRequest) -> dict[str, object]:
    with _db_conn() as conn:
        resolved_account_name = _resolve_backtest_payload_account(payload.account, conn)
        payload = payload.model_copy(update={"account": resolved_account_name})
        try:
            warnings = preview_backtest_warnings(conn, _backtest_config_from_preflight_request(payload))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except FileNotFoundError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return {
            "warnings": warnings,
        }


@app.post("/api/backtests/walk-forward")
def api_run_walk_forward(payload: WalkForwardRunRequest) -> dict[str, object]:
    with _db_conn() as conn:
        resolved_account_name = _resolve_backtest_payload_account(payload.account, conn)
        payload = payload.model_copy(update={"account": resolved_account_name})
        try:
            summary = run_walk_forward_backtest(conn, _walk_forward_config_from_request(payload))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        display_account_name = _display_account_name(summary.account_name)

        return {
            "accountName": display_account_name,
            "startDate": summary.start_date,
            "endDate": summary.end_date,
            "windowCount": summary.window_count,
            "runIds": summary.run_ids,
            "averageReturnPct": summary.average_return_pct,
            "medianReturnPct": summary.median_return_pct,
            "bestReturnPct": summary.best_return_pct,
            "worstReturnPct": summary.worst_return_pct,
        }
