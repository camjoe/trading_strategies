from pathlib import Path

import pytest

from infrastructure.database.backend import (
    DatabaseBackend,
    SQLiteBackend,
    get_backend,
    set_backend,
    use_backend,
)


class StubBackend(DatabaseBackend):
    def __init__(self) -> None:
        self.open_called = False

    def open_connection(self) -> object:
        self.open_called = True
        return object()


def test_open_connection_creates_parent_and_sets_row_factory(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "paper.db"
    backend = SQLiteBackend(db_path)

    conn = backend.open_connection()
    try:
        assert db_path.parent.exists()
        row = conn.execute("SELECT 1 AS n").fetchone()
        assert row is not None
        assert row["n"] == 1
    finally:
        conn.close()


def test_set_backend_replaces_active_backend() -> None:
    original = get_backend()
    replacement = StubBackend()
    try:
        set_backend(replacement)
        assert get_backend() is replacement
    finally:
        set_backend(original)


def test_stub_backend_open_connection_is_callable() -> None:
    backend = StubBackend()

    conn = backend.open_connection()

    assert backend.open_called is True
    assert conn is not None


def test_use_backend_restores_the_previous_backend() -> None:
    original = get_backend()
    replacement = StubBackend()

    with use_backend(replacement) as active:
        assert active is replacement
        assert get_backend() is replacement

    assert get_backend() is original


def test_use_backend_restores_the_previous_backend_on_error() -> None:
    original = get_backend()

    with pytest.raises(RuntimeError, match="boom"):
        with use_backend(StubBackend()):
            raise RuntimeError("boom")

    assert get_backend() is original
