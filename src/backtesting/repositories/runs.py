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
from trading.repositories.strategies import StrategyRepository

_RUN_COLUMNS = """
    r.id, r.run_name, r.start_date, r.end_date, r.created_at, r.slippage_bps, r.fee_per_trade,
    r.tickers_file, a.name AS account_name,
    COALESCE(s.strategy_key, 'unknown') AS strategy
"""


def insert_run(
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
    created_at: str | None = None,
    notes: str = "First working backtest version: deterministic daily-bar simulator.",
) -> int:
    # The backtested strategy is a strategies FK. The caller
    # passes the canonical strategy key (resolved via resolve_strategy in the
    # service); the catalog row is seeded, so this is a lookup, not a create.
    created_at = created_at or utc_now_iso()
    strategy_id = StrategyRepository(conn).ensure_id_for_label(label=strategy_name, now_iso=created_at)
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
            notes,
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


def insert_trade(
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


def insert_snapshot(
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


def fetch_runs(
    conn: sqlite3.Connection,
    *,
    limit: int,
    account_name: str | None = None,
) -> list[dict[str, object]]:
    """Standalone runs newest first, for one account or across all of them.

    Standalone-only: walk-forward OOS and holdout runs live in ``backtest_runs``
    too, but they are optimizer internals and must not surface as backtest history.

    Callers wanting the latest single run pass ``limit=1`` and read the first row —
    "newest" is this ordering, so a separate query for it would be the same query.
    """
    rows = conn.execute(
        f"""
        SELECT {_RUN_COLUMNS}
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        LEFT JOIN strategies s ON s.id = r.strategy_id
        WHERE r.purpose = ?
          AND (? IS NULL OR a.name = ?)
        ORDER BY r.id DESC
        LIMIT ?
        """,
        (BACKTEST_PURPOSE_STANDALONE, account_name, account_name, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_run(conn: sqlite3.Connection, run_id: int) -> dict[str, object] | None:
    row = conn.execute(
        f"""
        SELECT {_RUN_COLUMNS},
             r.notes, r.warnings, r.benchmark_ticker, r.benchmark_return_pct
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        LEFT JOIN strategies s ON s.id = r.strategy_id
        WHERE r.id = ?
        """,
        (run_id,),
    ).fetchone()
    return None if row is None else dict(row)


def fetch_snapshots(conn: sqlite3.Connection, run_id: int) -> list[dict[str, object]]:
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


def fetch_trades(conn: sqlite3.Connection, run_id: int) -> list[dict[str, object]]:
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


def fetch_run_equity_bounds(conn: sqlite3.Connection, *, run_id: int) -> tuple[float, float] | None:
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
    """The best *limit* standalone runs by total return, best first.

    Ranking and the limit are both applied here, over every matching run — taking
    the most recent *limit* rows and ordering those by return would answer a
    different question, and a run whose best result is old would never appear.

    Runs without usable equity bounds are dropped before the limit, so a full
    board is returned whenever that many rankable runs exist.

    *strategy* is a substring match, which is what reaches a base strategy's
    promoted variants (filtering ``trend`` finds ``trend_v1`` runs) — variant keys
    are operator-chosen and not in the code registry. The cost is that it also
    matches unrelated keys containing the filter: ``trend`` returns
    ``pullback_trend`` and ``volatility_filtered_trend`` runs too.
    """
    rows = conn.execute(
        """
        WITH ranked AS (
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
                    SELECT snap.equity
                    FROM backtest_equity_snapshots snap
                    WHERE snap.run_id = r.id
                    ORDER BY snap.snapshot_date ASC, snap.id ASC
                    LIMIT 1
                ) AS starting_equity,
                (
                    SELECT snap.equity
                    FROM backtest_equity_snapshots snap
                    WHERE snap.run_id = r.id
                    ORDER BY snap.snapshot_date DESC, snap.id DESC
                    LIMIT 1
                ) AS ending_equity
            FROM backtest_runs r
            JOIN accounts a ON a.id = r.account_id
            LEFT JOIN strategies s ON s.id = r.strategy_id
            WHERE r.purpose = ?
              AND (? IS NULL OR a.name = ?)
              AND (? IS NULL OR LOWER(COALESCE(s.strategy_key, 'unknown')) LIKE '%' || LOWER(?) || '%')
        )
        SELECT *
        FROM ranked
        WHERE starting_equity IS NOT NULL
          AND ending_equity IS NOT NULL
          AND starting_equity > 0
        ORDER BY (ending_equity * 1.0 / starting_equity) DESC, run_id DESC
        LIMIT ?
        """,
        (BACKTEST_PURPOSE_STANDALONE, account_name, account_name, strategy, strategy, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]
