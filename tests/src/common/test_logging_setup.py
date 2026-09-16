from __future__ import annotations

import logging
from pathlib import Path

import pytest

from common import logging_setup


@pytest.fixture(autouse=True)
def _restore_root_logger(monkeypatch):
    """Snapshot and restore the root logger so configure_logging cannot leak across tests."""
    root = logging.getLogger()
    # Drop any counting handler another test file's configure_logging left on the
    # root: these tests assert against a clean root, and xdist can schedule them on
    # a worker that already ran such a test. Without this, log_counts() reads the
    # leaked tally instead of zero.
    for handler in [h for h in root.handlers if isinstance(h, logging_setup._LevelCountingHandler)]:
        root.removeHandler(handler)
        handler.close()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    monkeypatch.delenv(logging_setup.RUN_ID_ENV, raising=False)
    monkeypatch.delenv(logging_setup.LOG_LEVEL_ENV, raising=False)
    logging_setup.bind_run_id("-")
    yield
    for handler in [h for h in root.handlers if h not in saved_handlers]:
        root.removeHandler(handler)
        handler.close()
    for handler in saved_handlers:
        if handler not in root.handlers:
            root.addHandler(handler)
    root.setLevel(saved_level)


def test_new_run_id_is_short_hex_and_distinct() -> None:
    first, second = logging_setup.new_run_id(), logging_setup.new_run_id()
    assert len(first) == 8 and int(first, 16) >= 0
    assert first != second


def test_resolve_run_id_prefers_environment(monkeypatch) -> None:
    monkeypatch.setenv(logging_setup.RUN_ID_ENV, "parent01")
    assert logging_setup.resolve_run_id() == "parent01"


def test_resolve_run_id_generates_when_unset() -> None:
    assert len(logging_setup.resolve_run_id()) == 8


def test_bind_run_id_sets_current_and_optionally_exports(monkeypatch) -> None:
    monkeypatch.delenv(logging_setup.RUN_ID_ENV, raising=False)
    logging_setup.bind_run_id("abcd1234")
    assert logging_setup.current_run_id() == "abcd1234"
    assert logging_setup.RUN_ID_ENV not in __import__("os").environ

    logging_setup.bind_run_id("exported9", export=True)
    assert __import__("os").environ[logging_setup.RUN_ID_ENV] == "exported9"


def test_configure_logging_writes_run_id_and_level_to_file(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "run.log"
    logging_setup.bind_run_id("run12345")
    logging_setup.configure_logging(log_file=log_file, level="DEBUG")

    logging.getLogger("trading.some.module").debug("hello world")
    for handler in logging.getLogger().handlers:
        handler.flush()

    text = log_file.read_text(encoding="utf-8")
    assert "hello world" in text
    assert "run=run12345" in text
    assert "DEBUG" in text
    assert "trading.some.module" in text


def test_configure_logging_is_idempotent_and_keeps_foreign_handlers(tmp_path: Path) -> None:
    root = logging.getLogger()
    foreign = logging.NullHandler()
    root.addHandler(foreign)

    logging_setup.configure_logging(log_file=tmp_path / "a.log")
    logging_setup.configure_logging(log_file=tmp_path / "b.log")

    managed = [h for h in root.handlers if getattr(h, logging_setup._MANAGED_FLAG, False)]
    # Each call adds a stream + file + counting handler, but the second removes the
    # first's — so exactly one trio remains, not six handlers.
    assert len(managed) == 3
    assert foreign in root.handlers


def test_configure_logging_level_falls_back_to_info_on_bad_value(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(logging_setup.LOG_LEVEL_ENV, "NONSENSE")
    logging_setup.configure_logging(log_file=tmp_path / "c.log")
    assert logging.getLogger().level == logging.INFO


def test_log_counts_tally_warning_and_worse_and_reset_per_configure(tmp_path: Path) -> None:
    logging_setup.configure_logging(log_file=tmp_path / "d.log", level="DEBUG")
    logger = logging.getLogger("trading.counted")
    logger.info("ignored by the counter")
    logger.warning("a warning")
    logger.error("an error")
    logger.critical("a critical")

    assert logging_setup.log_counts() == {"warning": 1, "error": 1, "critical": 1}

    # A fresh configure (a new run) resets the tally to zero.
    logging_setup.configure_logging(log_file=tmp_path / "e.log")
    assert logging_setup.log_counts() == {"warning": 0, "error": 0, "critical": 0}


def test_log_counts_zero_when_logging_never_configured() -> None:
    # The autouse fixture stripped managed handlers; no counter is present.
    assert logging_setup.log_counts() == {"warning": 0, "error": 0, "critical": 0}
