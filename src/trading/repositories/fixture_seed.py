"""Persistence operations for generated fixture databases (demo and sandbox).

Deliberately narrow. This holds only the writes that have no production writer
to route through — the research and review records a running system produces
through the backtest and promotion engines, plus the book bootstrap a fixture
needs but no operator flow exposes. Everything a running system derives
(fills, positions, ledger entries, book balances, snapshots, metrics) is written
by its owning service, not here; see ``trading.services.fixtures.seeding``.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence

from trading.repositories.unit_of_work import commit_unit_of_work

# Marks every synthetic backtest run so a generated row is never mistaken for a
# real research result.
FIXTURE_TICKERS_FILE = "synthetic:FIXTURE"

# Assessment/evaluation artifact versions on seeded promotion reviews. The
# `fixture-` prefix keeps them sortable alongside real versions while remaining
# obviously synthetic.
FIXTURE_ARTIFACT_VERSION = "fixture-v1"


class FixtureSeedRepository:
    """Write coherent synthetic records through one repository boundary."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def account_id(self, name: str) -> int:
        row = self._conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise ValueError(f"Fixture account '{name}' was not created.")
        return int(row["id"])

    def default_book_id(self, account_id: int) -> int:
        row = self._conn.execute(
            "SELECT id FROM books WHERE account_id = ? AND is_default = 1", (account_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Default book missing for fixture account {account_id}.")
        return int(row["id"])

    def set_account_paper_safety(self, account_id: int, *, now_iso: str) -> None:
        """Force a fixture account to paper with live trading disabled.

        Required by the Live Trading Safety Guard: no seeder may ever leave
        `live_trading_enabled` set, and every generated account is paper.
        """
        self._conn.execute(
            "UPDATE accounts SET broker_type = 'paper', live_trading_enabled = 0, updated_at = ? WHERE id = ?",
            (now_iso, account_id),
        )

    def fund_additional_book(
        self,
        *,
        account_id: int,
        default_book_id: int,
        name: str,
        trade_symbols: str,
        opening_cash: float,
        now_iso: str,
    ) -> int:
        """Create a non-default book, moving its opening cash off the default book.

        The account's capital is conserved: whatever the new book opens with is
        debited from the default book that account creation bootstrapped, so the
        sum across books still equals `accounts.initial_cash` and account-level
        replay stays consistent.

        The debit includes the default book's `start_equity`, not just its
        balances. Carve-outs happen before any trade, so the capital the default
        book *started* with is the capital left after funding the sleeves —
        leaving `start_equity` at the account's whole opening balance would make
        the default book's return read as a loss the size of the sleeves.
        """
        default_book = self._conn.execute(
            "SELECT start_equity, current_cash FROM books WHERE id = ?", (int(default_book_id),)
        ).fetchone()
        if default_book is None:
            raise ValueError(f"Default book {default_book_id} is missing; cannot fund '{name}'.")
        remaining = float(default_book["current_cash"]) - float(opening_cash)
        if remaining < 0:
            raise ValueError(
                f"Book '{name}' opening cash {opening_cash:.2f} exceeds the default book's "
                f"{float(default_book['current_cash']):.2f}."
            )
        remaining_start_equity = float(default_book["start_equity"]) - float(opening_cash)

        cursor = self._conn.execute(
            """INSERT INTO books
               (account_id, name, status, is_default, start_equity, current_cash, current_equity,
                trade_symbols, created_at, updated_at)
               VALUES (?, ?, 'active', 0, ?, ?, ?, ?, ?, ?)""",
            (account_id, name, opening_cash, opening_cash, opening_cash, trade_symbols, now_iso, now_iso),
        )
        book_id = cursor.lastrowid
        if book_id is None:
            raise ValueError(f"Expected a book id after inserting fixture book '{name}'.")
        self._conn.execute(
            "UPDATE books SET start_equity = ?, current_cash = ?, current_equity = ?, updated_at = ? WHERE id = ?",
            (remaining_start_equity, remaining, remaining, now_iso, int(default_book_id)),
        )
        commit_unit_of_work(self._conn)
        return int(book_id)

    def insert_backtest(
        self,
        *,
        account_id: int,
        strategy_key: str,
        start_date: str,
        end_date: str,
        snapshots: Sequence[tuple[str, float]],
        now_iso: str,
    ) -> None:
        strategy = self._conn.execute("SELECT id FROM strategies WHERE strategy_key = ?", (strategy_key,)).fetchone()
        if strategy is None:
            raise ValueError(f"Fixture strategy '{strategy_key}' is missing.")
        cursor = self._conn.execute(
            """INSERT INTO backtest_runs
               (account_id, strategy_id, run_name, purpose, start_date, end_date, created_at,
                slippage_bps, fee_per_trade, tickers_file, notes, warnings)
               VALUES (?, ?, 'Generated fixture backtest', 'standalone', ?, ?, ?, 2.5, 0,
                       ?, 'Deterministic synthetic fixture run.', '')""",
            (account_id, int(strategy["id"]), start_date, end_date, now_iso, FIXTURE_TICKERS_FILE),
        )
        run_id = cursor.lastrowid
        if run_id is None:
            raise ValueError("Expected a run id after inserting the fixture backtest.")
        first_date = snapshots[4][0]
        last_date = snapshots[-5][0]
        opening_equity = snapshots[0][1]
        self._conn.execute(
            """INSERT INTO backtest_executions
               (run_id, execution_date, ticker, side, qty, price, fee, slippage_bps, note)
               VALUES (?, ?, 'AAPL', 'buy', 12, 150, 0, 2.5, 'Synthetic sample execution')""",
            (run_id, first_date),
        )
        self._conn.execute(
            """INSERT INTO backtest_executions
               (run_id, execution_date, ticker, side, qty, price, fee, slippage_bps, note)
               VALUES (?, ?, 'AAPL', 'sell', 12, 162, 0, 2.5, 'Synthetic sample execution')""",
            (run_id, last_date),
        )
        for snapshot_date, equity in snapshots:
            self._conn.execute(
                """INSERT INTO backtest_equity_snapshots
                   (run_id, snapshot_date, cash, market_value, equity, realized_pnl, unrealized_pnl)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    snapshot_date,
                    equity * 0.35,
                    equity * 0.65,
                    equity,
                    max(0.0, equity - opening_equity) * 0.4,
                    0.0,
                ),
            )

    def insert_promotion_review(self, *, account_id: int, account_name: str, strategy_key: str, now_iso: str) -> None:
        strategy = self._conn.execute("SELECT id FROM strategies WHERE strategy_key = ?", (strategy_key,)).fetchone()
        if strategy is None:
            raise ValueError(f"Fixture strategy '{strategy_key}' is missing.")
        assessment = {"sample": True, "label": "Synthetic fixture evidence", "status": "ready_for_review"}
        evaluation = {"sample": True, "label": "Synthetic fixture evidence", "trade_count": 15, "snapshot_count": 30}
        cursor = self._conn.execute(
            """INSERT INTO promotion_reviews
               (account_id, account_name_snapshot, strategy_name, review_state, assessment_stage,
                assessment_status, ready_for_live, overall_confidence, live_trading_enabled_snapshot,
                promotion_assessment_version, evaluation_artifact_version, frozen_assessment_payload,
                frozen_evaluation_payload, requested_by, operator_summary_note, created_at, updated_at, strategy_id)
               VALUES (?, ?, ?, 'requested', 'promotion_review', 'ready_for_review', 0, 0.82, 0,
                       ?, ?, ?, ?, 'generated-fixture',
                       'Synthetic sample evidence only; not suitable for live-trading decisions.', ?, ?, ?)""",
            (
                account_id,
                account_name,
                strategy_key,
                FIXTURE_ARTIFACT_VERSION,
                FIXTURE_ARTIFACT_VERSION,
                json.dumps(assessment),
                json.dumps(evaluation),
                now_iso,
                now_iso,
                int(strategy["id"]),
            ),
        )
        review_id = cursor.lastrowid
        if review_id is None:
            raise ValueError("Expected a review id after inserting the fixture promotion review.")
        # A review with no events is an unreachable state in the real workflow:
        # the request that creates it is itself the first recorded transition.
        self._conn.execute(
            """INSERT INTO promotion_review_events
               (review_id, event_seq, event_type, actor_type, actor_name, from_review_state,
                to_review_state, note, created_at)
               VALUES (?, 1, 'requested', 'operator', 'generated-fixture', NULL, 'requested',
                       'Generated fixture review request.', ?)""",
            (review_id, now_iso),
        )
