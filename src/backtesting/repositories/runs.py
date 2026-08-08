"""SQL for a backtest run: its header, executions, and equity snapshots.

Reads return plain dicts, not ``sqlite3.Row``: a ``Row`` is not a ``Mapping``
(no ``get``/``items``/``values``, and iterating it yields values rather than
keys), so handing one to a caller annotated for ``Mapping`` promises an
interface it does not have.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from backtesting.models import BACKTEST_PURPOSE_STANDALONE, BacktestConfig
from common.time import utc_now_iso
from trading.persistence.unit_of_work import commit_unit_of_work
from trading.repositories.book_bridge import strategy_id_for_label

_REPORT_COLUMNS = """
    r.id, r.run_name, r.start_date, r.end_date, r.created_at, r.slippage_bps, r.fee_per_trade,
    r.tickers_file, a.name AS account_name,
    COALESCE(s.strategy_key, 'unknown') AS strategy
"""


def insert_backtest_run(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_name: str,
    start_date: date,
    end_date: date,
    cfg: BacktestConfig,
    warnings: list[str],
    benchmark_ticker: str,
    benchmark_return_pct: float | None,
) -> int:
    # The backtested strategy is a strategies FK. The caller
    # passes the canonical strategy key (resolved via resolve_strategy in the
    # service); the catalog row is seeded, so this is a lookup, not a create.
    created_at = utc_now_iso()
    strategy_id = strategy_id_for_label(conn, strategy_name, now_iso=created_at)
    cursor = conn.execute(
        """
        INSERT INTO backtest_runs (
            account_id,
            strategy_id,
            run_name,
            purpose,
            start_date,
            end_date,
            created_at,
            slippage_bps,
            fee_per_trade,
            tickers_file,
            notes,
            warnings,
            benchmark_ticker,
            benchmark_return_pct
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            strategy_id,
            cfg.run_name,
            cfg.purpose,
            start_date.isoformat(),
            end_date.isoformat(),
            created_at,
            float(cfg.slippage_bps),
            float(cfg.fee_per_trade),
            cfg.tickers_file,
            "First working backtest version: deterministic daily-bar simulator.",
            " | ".join(warnings),
            benchmark_ticker,
            benchmark_return_pct,
        ),
    )
    # Participates in the run's unit_of_work: commits standalone, defers inside a
    # scope so the header, executions, and snapshots land together or not at all.
    commit_unit_of_work(conn)
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def insert_backtest_trade(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    trade_time: str,
    ticker: str,
    side: str,
    qty: float,
    price: float,
    fee: float,
    slippage_bps: float,
    note: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO backtest_executions (
            run_id, execution_date, ticker, side, qty, price, fee, slippage_bps, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, trade_time, ticker, side, qty, price, fee, slippage_bps, note),
    )
    commit_unit_of_work(conn)


def insert_backtest_snapshot(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    snapshot_time: str,
    cash: float,
    market_value: float,
    equity: float,
    realized_pnl: float,
    unrealized_pnl: float,
) -> None:
    conn.execute(
        """
        INSERT INTO backtest_equity_snapshots (
            run_id, snapshot_date, cash, market_value, equity, realized_pnl, unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl),
    )
    commit_unit_of_work(conn)


def fetch_recent_backtest_runs(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, object]]:
    # Standalone-only: rolling-window (walk-forward) runs live in backtest_runs
    # too, but must not surface as generic recent backtests.
    rows = conn.execute(
        f"""
        SELECT {_REPORT_COLUMNS}
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        LEFT JOIN strategies s ON s.id = r.strategy_id
        WHERE r.purpose = ?
        ORDER BY r.id DESC
        LIMIT ?
        """,
        (BACKTEST_PURPOSE_STANDALONE, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_latest_backtest_run_for_account(conn: sqlite3.Connection, *, account_name: str) -> dict[str, object] | None:
    row = conn.execute(
        f"""
        SELECT {_REPORT_COLUMNS}
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        LEFT JOIN strategies s ON s.id = r.strategy_id
        WHERE a.name = ?
          AND r.purpose = ?
        ORDER BY r.id DESC
        LIMIT 1
        """,
        (account_name, BACKTEST_PURPOSE_STANDALONE),
    ).fetchone()
    return None if row is None else dict(row)


def fetch_latest_backtest_run_id_for_account(conn: sqlite3.Connection, *, account_name: str) -> int | None:
    row = conn.execute(
        """
        SELECT r.id
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        WHERE a.name = ?
          AND r.purpose = ?
        ORDER BY r.id DESC
        LIMIT 1
        """,
        (account_name, BACKTEST_PURPOSE_STANDALONE),
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def fetch_backtest_report_run(conn: sqlite3.Connection, run_id: int) -> dict[str, object] | None:
    row = conn.execute(
        f"""
        SELECT {_REPORT_COLUMNS},
             r.notes, r.warnings, r.benchmark_ticker, r.benchmark_return_pct
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        LEFT JOIN strategies s ON s.id = r.strategy_id
        WHERE r.id = ?
        """,
        (run_id,),
    ).fetchone()
    return None if row is None else dict(row)


def fetch_backtest_report_snapshots(conn: sqlite3.Connection, run_id: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT snapshot_date AS snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        FROM backtest_equity_snapshots
        WHERE run_id = ?
        ORDER BY snapshot_date ASC, id ASC
        """,
        (run_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_backtest_report_trades(conn: sqlite3.Connection, run_id: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT execution_date AS trade_time, ticker, side, qty, price, fee
        FROM backtest_executions
        WHERE run_id = ?
        ORDER BY execution_date, id
        """,
        (run_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_backtest_run_equity_bounds(conn: sqlite3.Connection, *, run_id: int) -> tuple[float, float] | None:
    """Return a run's ``(first_equity, last_equity)`` by snapshot date, or ``None``.

    The two equity marks needed to derive a run's total return without loading its
    whole equity curve. ``None`` when the run has no equity snapshots.
    """
    row = conn.execute(
        """
        SELECT
            (SELECT equity FROM backtest_equity_snapshots
             WHERE run_id = ? ORDER BY snapshot_date ASC, id ASC LIMIT 1) AS first_equity,
            (SELECT equity FROM backtest_equity_snapshots
             WHERE run_id = ? ORDER BY snapshot_date DESC, id DESC LIMIT 1) AS last_equity
        """,
        (int(run_id), int(run_id)),
    ).fetchone()
    if row is None or row["first_equity"] is None or row["last_equity"] is None:
        return None
    return (float(row["first_equity"]), float(row["last_equity"]))


def fetch_leaderboard_rows(
    conn: sqlite3.Connection,
    *,
    limit: int,
    account_name: str | None,
    strategy: str | None,
) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT
            r.id AS run_id,
            r.run_name,
            r.start_date,
            r.end_date,
            r.created_at,
            a.name AS account_name,
            COALESCE(s.strategy_key, 'unknown') AS strategy,
            r.benchmark_return_pct,
            (
                SELECT s.equity
                FROM backtest_equity_snapshots s
                WHERE s.run_id = r.id
                ORDER BY s.snapshot_date ASC, s.id ASC
                LIMIT 1
            ) AS starting_equity,
            (
                SELECT s.equity
                FROM backtest_equity_snapshots s
                WHERE s.run_id = r.id
                ORDER BY s.snapshot_date DESC, s.id DESC
                LIMIT 1
            ) AS ending_equity,
            (
                SELECT COUNT(*)
                FROM backtest_executions t
                WHERE t.run_id = r.id
            ) AS trade_count
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        LEFT JOIN strategies s ON s.id = r.strategy_id
        WHERE r.purpose = ?
          AND (? IS NULL OR a.name = ?)
          AND (? IS NULL OR LOWER(COALESCE(s.strategy_key, 'unknown')) LIKE '%' || LOWER(?) || '%')
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT ?
        """,
        (BACKTEST_PURPOSE_STANDALONE, account_name, account_name, strategy, strategy, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]
