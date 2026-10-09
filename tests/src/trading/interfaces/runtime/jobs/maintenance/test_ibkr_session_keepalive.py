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


def run_scripted(outcomes: list[Exception | None]):
    """Run the loop over scripted tickle outcomes; return the alerts it raised."""
    client = FakeClient(outcomes)
    alerts: list[tuple[object, str]] = []
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == len(outcomes):
            raise StopLoop

    with pytest.raises(StopLoop):
        module.run_keepalive(
            client,
            interval_seconds=60.0,
            notify=lambda state, detail: alerts.append((state, detail)),
            sleep=sleep,
        )
    assert sleeps == [60.0] * len(outcomes)
    return alerts


def test_run_keepalive_logs_only_state_changes(caplog) -> None:
    outcomes = [None, None, RuntimeError("not authenticated"), RuntimeError("not authenticated"), None]

    with caplog.at_level(logging.INFO, logger=KEEPALIVE_MODULE):
        run_scripted(outcomes)

    assert [(record.levelno, record.getMessage()) for record in caplog.records] == [
        (logging.INFO, "IBKR session alive"),
        (logging.WARNING, "IBKR session rejected: not authenticated"),
        (logging.INFO, "IBKR session alive"),
    ]


def test_a_healthy_start_sends_no_alert() -> None:
    assert run_scripted([None, None, None]) == []


def test_alerts_once_when_the_session_is_lost_and_once_when_it_recovers() -> None:
    lost = RuntimeError("not authenticated")

    alerts = run_scripted([None, lost, lost, lost, None])

    assert alerts == [
        (module.SessionState.REJECTED, "not authenticated"),
        (module.SessionState.ALIVE, ""),
    ]


def test_a_start_with_the_session_already_down_alerts() -> None:
    alerts = run_scripted([RuntimeError("not authenticated")])

    assert alerts == [(module.SessionState.REJECTED, "not authenticated")]


def test_a_move_from_rejected_to_unreachable_alerts_again() -> None:
    alerts = run_scripted([RuntimeError("not authenticated"), httpx.ConnectError("refused")])

    assert [state for state, _detail in alerts] == [module.SessionState.REJECTED, module.SessionState.UNREACHABLE]


def test_send_state_alert_tells_the_operator_what_to_do(monkeypatch) -> None:
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(module, "notify_runtime_event", lambda **kwargs: sent.append(kwargs) or True)

    module.send_state_alert(
        module.SessionState.REJECTED, "not authenticated", webhook_url="https://example.test/hook", email_config=None
    )
    module.send_state_alert(module.SessionState.UNREACHABLE, "refused", webhook_url=None, email_config=None)
    module.send_state_alert(module.SessionState.ALIVE, "", webhook_url=None, email_config=None)

    assert [(call["status"], call["message"]) for call in sent] == [
        ("fail", "IBKR session rejected: not authenticated. Log in at the Client Portal gateway."),
        ("fail", "IBKR session unreachable: refused. Start the Client Portal gateway and log in."),
        ("ok", "IBKR session alive again"),
    ]
    assert sent[0]["webhook_url"] == "https://example.test/hook"
    assert {call["event"] for call in sent} == {"ibkr-session-keepalive"}
