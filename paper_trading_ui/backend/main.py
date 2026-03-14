from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from trading.accounting import load_trades
from trading.backtesting.backtest import (
    BacktestConfig,
    backtest_report,
    run_backtest,
    WalkForwardConfig,
    run_walk_forward_backtest,
)
from trading.db import ensure_db
from trading.reporting import build_account_stats, snapshot_account

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parent

load_dotenv(BACKEND_DIR / ".env")


def _parse_cors_origins(raw: str) -> list[str]:
    cleaned = [item.strip() for item in raw.split(",") if item.strip()]
    return cleaned or ["*"]


logs_dir_raw = os.getenv("LOGS_DIR", "logs")
LOGS_DIR = (ROOT_DIR / logs_dir_raw).resolve() if not Path(logs_dir_raw).is_absolute() else Path(logs_dir_raw).resolve()
cors_origins = _parse_cors_origins(os.getenv("CORS_ORIGINS", "*"))

app = FastAPI(title="Paper Trading UI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    return {
        "runId": int(row["id"]),
        "runName": row["run_name"],
        "accountName": row["account_name"],
        "strategy": row["strategy"],
        "startDate": row["start_date"],
        "endDate": row["end_date"],
        "createdAt": row["created_at"],
        "slippageBps": float(row["slippage_bps"]),
        "feePerTrade": float(row["fee_per_trade"]),
        "tickersFile": row["tickers_file"],
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/accounts")
def api_accounts() -> dict[str, list[dict[str, object]]]:
    conn = ensure_db()
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM accounts
            ORDER BY name
            """
        ).fetchall()
        accounts = [_build_account_summary(conn, r) for r in rows]
        return {"accounts": accounts}
    finally:
        conn.close()


@app.get("/api/accounts/{account_name}")
def api_account_detail(account_name: str) -> dict[str, object]:
    conn = ensure_db()
    try:
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
            "snapshots": [
                {
                    "time": s["snapshot_time"],
                    "cash": float(s["cash"]),
                    "marketValue": float(s["market_value"]),
                    "equity": float(s["equity"]),
                    "realizedPnl": float(s["realized_pnl"]),
                    "unrealizedPnl": float(s["unrealized_pnl"]),
                }
                for s in snapshots
            ],
            "trades": [
                {
                    "ticker": t["ticker"],
                    "side": t["side"],
                    "qty": float(t["qty"]),
                    "price": float(t["price"]),
                    "fee": float(t["fee"]),
                    "tradeTime": t["trade_time"],
                }
                for t in trades[-100:]
            ],
        }
    finally:
        conn.close()


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
    conn = ensure_db()
    try:
        _ = _account_row(conn, account_name)
        snapshot_account(conn, account_name, snapshot_time=None)
        return {"status": "ok", "message": f"Snapshot saved for {account_name}"}
    finally:
        conn.close()


@app.post("/api/actions/snapshot-all")
def api_snapshot_all() -> dict[str, object]:
    conn = ensure_db()
    try:
        rows = conn.execute("SELECT name FROM accounts ORDER BY name").fetchall()
        names = [str(r["name"]) for r in rows]
        for name in names:
            snapshot_account(conn, name, snapshot_time=None)
        return {"status": "ok", "snapshotted": names}
    finally:
        conn.close()


@app.get("/api/backtests/runs")
def api_backtest_runs(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, list[dict[str, object]]]:
    conn = ensure_db()
    try:
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
        return {
            "runs": [
                {
                    "runId": int(r["id"]),
                    "runName": r["run_name"],
                    "accountName": r["account_name"],
                    "strategy": r["strategy"],
                    "startDate": r["start_date"],
                    "endDate": r["end_date"],
                    "createdAt": r["created_at"],
                    "slippageBps": float(r["slippage_bps"]),
                    "feePerTrade": float(r["fee_per_trade"]),
                    "tickersFile": r["tickers_file"],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


@app.get("/api/backtests/latest/{account_name}")
def api_latest_backtest_for_account(account_name: str) -> dict[str, object]:
    conn = ensure_db()
    try:
        _ = _account_row(conn, account_name)
        latest = _latest_backtest_summary(conn, account_name)
        return {
            "accountName": account_name,
            "latestRun": latest,
        }
    finally:
        conn.close()


@app.get("/api/backtests/runs/{run_id}")
def api_backtest_run_report(run_id: int) -> dict[str, object]:
    conn = ensure_db()
    try:
        try:
            return backtest_report(conn, run_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
    finally:
        conn.close()


@app.post("/api/backtests/run")
def api_run_backtest(payload: BacktestRunRequest) -> dict[str, object]:
    conn = ensure_db()
    try:
        try:
            result = run_backtest(
                conn,
                BacktestConfig(
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
                ),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return {
            "runId": result.run_id,
            "accountName": result.account_name,
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
    finally:
        conn.close()


@app.post("/api/backtests/walk-forward")
def api_run_walk_forward(payload: WalkForwardRunRequest) -> dict[str, object]:
    conn = ensure_db()
    try:
        try:
            summary = run_walk_forward_backtest(
                conn,
                WalkForwardConfig(
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
                ),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return {
            "accountName": summary.account_name,
            "startDate": summary.start_date,
            "endDate": summary.end_date,
            "windowCount": summary.window_count,
            "runIds": summary.run_ids,
            "averageReturnPct": summary.average_return_pct,
            "medianReturnPct": summary.median_return_pct,
            "bestReturnPct": summary.best_return_pct,
            "worstReturnPct": summary.worst_return_pct,
        }
    finally:
        conn.close()
