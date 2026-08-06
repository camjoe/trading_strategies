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


def test_default_backend_tracks_the_environment_after_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The module-level default backend is constructed at import time. It must
    # resolve its path per access, or a TRADING_DB_PATH set afterwards moves
    # get_db_path() while leaving the backend pointed at the old database.
    backend = SQLiteBackend()
    monkeypatch.setenv("TRADING_DB_PATH", str(tmp_path / "switched.db"))

    assert backend.db_path == (tmp_path / "switched.db").resolve()


def test_explicit_path_is_not_affected_by_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pinned = tmp_path / "pinned.db"
    backend = SQLiteBackend(pinned)
    monkeypatch.setenv("TRADING_DB_PATH", str(tmp_path / "ignored.db"))

    assert backend.db_path == pinned


def test_use_backend_restores_the_previous_backend_on_error() -> None:
    original = get_backend()

    with pytest.raises(RuntimeError, match="boom"):
        with use_backend(StubBackend()):
            raise RuntimeError("boom")

    assert get_backend() is original
