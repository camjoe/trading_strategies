from __future__ import annotations

import logging

import httpx
import pytest

from tests.src.trading.interfaces.runtime.jobs.loaders import load_runtime_job

KEEPALIVE_MODULE = "trading.interfaces.runtime.jobs.maintenance.ibkr_session_keepalive"
module = load_runtime_job(KEEPALIVE_MODULE)


class StopLoop(Exception):
    pass


class FakeClient:
    """Plays one scripted outcome per tickle: None for a live session, or an exception."""

    def __init__(self, outcomes: list[Exception | None]) -> None:
        self._outcomes = list(outcomes)
        self.tickles = 0

    def tickle(self) -> dict[str, object]:
        self.tickles += 1
        outcome = self._outcomes.pop(0)
        if outcome is not None:
            raise outcome
        return {}

    def validate_session(self) -> None:
        pass


def test_check_session_reports_a_live_session() -> None:
    assert module.check_session(FakeClient([None])) == (module.SessionState.ALIVE, "")


def test_check_session_reports_a_rejected_session() -> None:
    client = FakeClient([RuntimeError("IBKR Web API session is not authenticated.")])

    state, detail = module.check_session(client)

    assert state is module.SessionState.REJECTED
    assert detail == "IBKR Web API session is not authenticated."


def test_check_session_reports_an_unreachable_gateway() -> None:
    client = FakeClient([httpx.ConnectError("[Errno 111] Connection refused")])

    state, detail = module.check_session(client)

    assert state is module.SessionState.UNREACHABLE
    assert "Connection refused" in detail


def test_run_keepalive_logs_only_state_changes(caplog) -> None:
    client = FakeClient([None, None, RuntimeError("not authenticated"), RuntimeError("not authenticated"), None])
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 5:
            raise StopLoop

    with caplog.at_level(logging.INFO, logger=KEEPALIVE_MODULE), pytest.raises(StopLoop):
        module.run_keepalive(client, interval_seconds=60.0, sleep=sleep)

    assert client.tickles == 5
    assert sleeps == [60.0] * 5
    assert [(record.levelno, record.getMessage()) for record in caplog.records] == [
        (logging.INFO, "IBKR session alive"),
        (logging.WARNING, "IBKR session rejected: not authenticated"),
        (logging.INFO, "IBKR session alive"),
    ]
