"""Central logging configuration for runtime jobs.

Configure the stdlib root logger once per process so modules that use
``logging.getLogger(__name__)`` land in the job's per-run log file and on stdout,
correlated by a run id. Without this the library loggers under ``infrastructure``
and ``services`` have no handler and their output is dropped.

The jobs' own operational lines still go through ``tee_line``; this captures
everything else that would otherwise be lost, in the same file, tagged with the
same ``run_id``. A parent that shells out to a worker exports ``TRADING_RUN_ID``
so the worker's log lines carry the parent's id.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import TextIO

# Env var carrying the level (e.g. "DEBUG"); defaults to INFO when unset/invalid.
LOG_LEVEL_ENV = "TRADING_LOG_LEVEL"
DEFAULT_LOG_LEVEL = "INFO"

# Env var a parent process sets so a shelled-out worker shares its run id.
RUN_ID_ENV = "TRADING_RUN_ID"

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [run=%(run_id)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

# Marks handlers this module installs, so a repeated configure removes only its
# own handlers and leaves foreign ones (e.g. pytest's caplog) in place.
_MANAGED_FLAG = "_trading_managed"

_RUN_ID: ContextVar[str] = ContextVar("run_id", default="-")


class _RunIdFilter(logging.Filter):
    """Stamp the current run id onto every record so the formatter can render it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = _RUN_ID.get()
        return True


class _LevelCountingHandler(logging.Handler):
    """Tally WARNING and worse records so a run can report how many it emitted.

    This is how "how many exceptions/warnings this run" is answered without
    instrumenting every ``except``: the provider/service loggers already route
    through the root logger (see ``configure_logging``), so their WARNING+ records
    are counted here and read back via ``log_counts`` at the end of the run.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.counts: dict[str, int] = {}

    def emit(self, record: logging.LogRecord) -> None:
        self.counts[record.levelname] = self.counts.get(record.levelname, 0) + 1


def log_counts() -> dict[str, int]:
    """Return WARNING/ERROR/CRITICAL counts recorded since the last configure.

    Zeros when logging was never configured this process, so a caller can always
    write the fields into an artifact.
    """
    for handler in logging.getLogger().handlers:
        if isinstance(handler, _LevelCountingHandler):
            counts = handler.counts
            return {
                "warning": counts.get("WARNING", 0),
                "error": counts.get("ERROR", 0),
                "critical": counts.get("CRITICAL", 0),
            }
    return {"warning": 0, "error": 0, "critical": 0}


def new_run_id() -> str:
    """Return a short random run id."""
    return uuid.uuid4().hex[:8]


def resolve_run_id() -> str:
    """Return the inherited run id from the environment, or a new one."""
    inherited = os.getenv(RUN_ID_ENV, "").strip()
    return inherited or new_run_id()


def bind_run_id(run_id: str, *, export: bool = False) -> str:
    """Bind *run_id* for this process's log lines; optionally export it to children.

    ``export`` sets ``TRADING_RUN_ID`` so a subprocess started later inherits the
    same id and its teed-back output stays correlated.
    """
    _RUN_ID.set(run_id)
    if export:
        os.environ[RUN_ID_ENV] = run_id
    return run_id


def current_run_id() -> str:
    return _RUN_ID.get()


def _resolve_level(level: str | None) -> int:
    name = (level or os.getenv(LOG_LEVEL_ENV) or DEFAULT_LOG_LEVEL).strip().upper()
    resolved = logging.getLevelName(name)
    # getLevelName returns an int for a known name, else the string "Level <name>".
    return resolved if isinstance(resolved, int) else logging.INFO


def configure_logging(
    *,
    log_file: Path | None = None,
    level: str | None = None,
    stream: TextIO | None = None,
) -> None:
    """Configure the root logger: a stream handler and an optional file handler.

    Idempotent — a repeated call removes the handlers a previous call installed
    before adding fresh ones, so running several jobs in one process (or repeated
    test calls) does not stack duplicates. Foreign handlers are left untouched.
    """
    root = logging.getLogger()
    root.setLevel(_resolve_level(level))

    for handler in [h for h in root.handlers if getattr(h, _MANAGED_FLAG, False)]:
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
    run_filter = _RunIdFilter()

    stream_handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(run_filter)
    setattr(stream_handler, _MANAGED_FLAG, True)
    root.addHandler(stream_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.addFilter(run_filter)
        setattr(file_handler, _MANAGED_FLAG, True)
        root.addHandler(file_handler)

    # Reset per configure (once per run): the managed-handler cleanup above dropped
    # any prior counter, so this run starts its WARNING+ tally from zero.
    counting_handler = _LevelCountingHandler()
    setattr(counting_handler, _MANAGED_FLAG, True)
    root.addHandler(counting_handler)
