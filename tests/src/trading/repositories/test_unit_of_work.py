from __future__ import annotations

import sqlite3

import pytest

from trading.repositories.unit_of_work import maybe_commit, unit_of_work


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT NOT NULL)")
    c.commit()
    return c


def _count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM t").fetchone()[0])


def test_maybe_commit_persists_when_standalone(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO t (v) VALUES ('a')")
    maybe_commit(conn)
    conn.rollback()  # nothing pending; the row was already committed
    assert _count(conn) == 1


def test_unit_of_work_commits_once_on_clean_exit(conn: sqlite3.Connection) -> None:
    with unit_of_work(conn):
        conn.execute("INSERT INTO t (v) VALUES ('a')")
        maybe_commit(conn)  # suppressed inside the scope
        conn.execute("INSERT INTO t (v) VALUES ('b')")
        maybe_commit(conn)
        assert _count(conn) == 2  # visible within the open transaction
    conn.rollback()  # committed already, so this is a no-op
    assert _count(conn) == 2


def test_unit_of_work_rolls_back_all_writes_on_error(conn: sqlite3.Connection) -> None:
    with pytest.raises(RuntimeError):
        with unit_of_work(conn):
            conn.execute("INSERT INTO t (v) VALUES ('a')")
            maybe_commit(conn)
            conn.execute("INSERT INTO t (v) VALUES ('b')")
            maybe_commit(conn)
            raise RuntimeError("boom")
    assert _count(conn) == 0


def test_nested_scope_joins_outer_transaction(conn: sqlite3.Connection) -> None:
    with unit_of_work(conn):
        conn.execute("INSERT INTO t (v) VALUES ('outer')")
        maybe_commit(conn)
        with unit_of_work(conn):
            conn.execute("INSERT INTO t (v) VALUES ('inner')")
            maybe_commit(conn)
        # inner exit must NOT have committed — a later failure still rolls both back
    assert _count(conn) == 2


def test_error_in_nested_scope_rolls_back_everything(conn: sqlite3.Connection) -> None:
    with pytest.raises(RuntimeError):
        with unit_of_work(conn):
            conn.execute("INSERT INTO t (v) VALUES ('outer')")
            maybe_commit(conn)
            with unit_of_work(conn):
                conn.execute("INSERT INTO t (v) VALUES ('inner')")
                maybe_commit(conn)
                raise RuntimeError("boom")
    assert _count(conn) == 0
