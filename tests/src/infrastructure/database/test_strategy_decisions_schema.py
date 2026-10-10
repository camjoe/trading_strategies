"""strategy_decisions: write-once decision fields, outcome updates, and delete actions."""

from __future__ import annotations

import sqlite3

import pytest

_TS = "2026-10-01T00:00:00Z"


def _seed(conn: sqlite3.Connection) -> dict[str, int]:
    account_id = conn.execute(
        "INSERT INTO accounts (name, initial_cash, created_at, updated_at) VALUES ('acct', 1000, ?, ?)",
        (_TS, _TS),
    ).lastrowid
    book_id = conn.execute(
        "INSERT INTO books (account_id, name, start_equity, current_cash, current_equity, trade_symbols,"
        " created_at, updated_at) VALUES (?, 'book', 1000, 1000, 1000, '[]', ?, ?)",
        (account_id, _TS, _TS),
    ).lastrowid
    strategy_id = conn.execute(
        "INSERT INTO strategies (strategy_key, primitive, params_json, created_at, updated_at)"
        " VALUES ('trend_k', 'trend', '{}', ?, ?)",
        (_TS, _TS),
    ).lastrowid
    review_id = conn.execute(
        "INSERT INTO promotion_reviews (account_id, account_name_snapshot, strategy_name, assessment_stage,"
        " assessment_status, promotion_assessment_version, evaluation_artifact_version,"
        " frozen_assessment_payload, frozen_evaluation_payload, created_at, updated_at)"
        " VALUES (?, 'acct', 'trend_k', 's', 's', 'v', 'v', '{}', '{}', ?, ?)",
        (account_id, _TS, _TS),
    ).lastrowid
    decision_id = conn.execute(
        "INSERT INTO strategy_decisions (account_id, book_id, strategy_id, decision_type, rationale,"
        " evidence_json, optimization_experiment_id, promotion_review_id, decided_by, created_at)"
        " VALUES (?, ?, ?, 'hold', 'evidence is stale', '{}', 99, ?, 'agent', ?)",
        (account_id, book_id, strategy_id, review_id, _TS),
    ).lastrowid
    return {
        "account": int(account_id or 0),
        "book": int(book_id or 0),
        "review": int(review_id or 0),
        "decision": int(decision_id or 0),
    }


def _column(conn: sqlite3.Connection, decision_id: int, column: str) -> object:
    return conn.execute(f"SELECT {column} FROM strategy_decisions WHERE id = ?", (decision_id,)).fetchone()[0]


def test_new_decision_defaults_to_pending_with_a_21_day_window(conn: sqlite3.Connection) -> None:
    ids = _seed(conn)
    assert _column(conn, ids["decision"], "outcome_status") == "pending"
    assert _column(conn, ids["decision"], "outcome_window_days") == 21


def test_outcome_columns_can_be_scored(conn: sqlite3.Connection) -> None:
    ids = _seed(conn)
    conn.execute(
        "UPDATE strategy_decisions SET outcome_status = 'measured', outcome_verdict = 'neutral',"
        " outcome_measured_at = ?, realized_return_pct = 1.5 WHERE id = ?",
        (_TS, ids["decision"]),
    )
    assert _column(conn, ids["decision"], "outcome_verdict") == "neutral"


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("rationale", "rewritten after the fact"),
        ("evidence_json", '{"edited": true}'),
        ("decision_type", "adjust_params"),
        ("decided_by", "someone_else"),
        ("outcome_window_days", 5),
        ("alternative_strategy_id", 999),
    ],
)
def test_decision_fields_are_write_once(conn: sqlite3.Connection, column: str, value: object) -> None:
    ids = _seed(conn)
    with pytest.raises(sqlite3.IntegrityError, match="write-once"):
        conn.execute(f"UPDATE strategy_decisions SET {column} = ? WHERE id = ?", (value, ids["decision"]))


def test_book_link_cannot_be_repointed(conn: sqlite3.Connection) -> None:
    ids = _seed(conn)
    with pytest.raises(sqlite3.IntegrityError, match="write-once"):
        conn.execute("UPDATE strategy_decisions SET book_id = ? WHERE id = ?", (ids["book"] + 1, ids["decision"]))


def test_measured_outcome_requires_a_verdict(conn: sqlite3.Connection) -> None:
    ids = _seed(conn)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute(
            "UPDATE strategy_decisions SET outcome_status = 'measured', outcome_measured_at = ? WHERE id = ?",
            (_TS, ids["decision"]),
        )


def test_deleting_the_book_or_review_keeps_the_decision(conn: sqlite3.Connection) -> None:
    ids = _seed(conn)
    conn.execute("DELETE FROM promotion_reviews WHERE id = ?", (ids["review"],))
    conn.execute("DELETE FROM books WHERE id = ?", (ids["book"],))

    assert _column(conn, ids["decision"], "book_id") is None
    assert _column(conn, ids["decision"], "promotion_review_id") is None
    assert _column(conn, ids["decision"], "rationale") == "evidence is stale"


def test_deleting_the_account_removes_its_decisions(conn: sqlite3.Connection) -> None:
    ids = _seed(conn)
    conn.execute("DELETE FROM accounts WHERE id = ?", (ids["account"],))
    assert conn.execute("SELECT COUNT(*) FROM strategy_decisions").fetchone()[0] == 0


def test_counterfactual_arm_returns_are_outcome_columns(conn: sqlite3.Connection) -> None:
    ids = _seed(conn)
    conn.execute(
        "UPDATE strategy_decisions SET chosen_return_pct = 4.0, alternative_return_pct = 1.0 WHERE id = ?",
        (ids["decision"],),
    )
    assert _column(conn, ids["decision"], "chosen_return_pct") == 4.0
