"""Fixtures for end-to-end tests that drive the real CLI entrypoint.

A test builds a database at the head revision, points the active backend at
it, forces the deterministic ``demo`` market-data provider, then runs
``trading.interfaces.cli.main.main`` with a chosen argument vector. The demo
provider makes no network call, so a run is reproducible.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from infrastructure.database.backend import SQLiteBackend, use_backend
from tests.support.db_schema import build_db_at_head


@pytest.fixture
def cli_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Activate a fresh head-revision database and the deterministic provider.

    The CLI opens its own ``db_session`` per run, so the test seeds through a
    short-lived connection and lets ``main`` open the same file independently.
    """
    db_path = build_db_at_head(tmp_path / "cli_e2e.db")
    monkeypatch.setenv("TRADING_MARKET_DATA_PROVIDER", "demo")
    with use_backend(SQLiteBackend(db_path)):
        yield db_path


@pytest.fixture
def run_cli(
    cli_backend: Path,  # noqa: ARG001 — activates the backend + provider
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Callable[..., str]:
    """Return a callable that runs the CLI with *argv* and returns stdout."""

    def _run(*argv: str) -> str:
        from trading.interfaces.cli.main import main

        monkeypatch.setattr(sys, "argv", ["trading", *argv])
        main()
        return capsys.readouterr().out

    return _run
