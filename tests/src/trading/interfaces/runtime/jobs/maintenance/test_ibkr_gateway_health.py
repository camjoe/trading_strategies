from __future__ import annotations

import logging

import pytest

from tests.src.trading.interfaces.runtime.jobs.loaders import load_runtime_job

HEALTH_MODULE = "trading.interfaces.runtime.jobs.maintenance.ibkr_gateway_health"
module = load_runtime_job(HEALTH_MODULE)


class StopLoop(Exception):
    pass


class FakeClient:
    """Plays one scripted outcome per connect: a list of accounts, or an exception."""

    def __init__(self, outcome: list[str] | Exception, *, disconnect_error: Exception | None = None) -> None:
        self._outcome = outcome
        self._disconnect_error = disconnect_error
        self.connected_with: tuple[str, int, int] | None = None
        self.disconnects = 0

    def connect(self, host: str, port: int, *, client_id: int) -> None:
        self.connected_with = (host, port, client_id)
        if isinstance(self._outcome, Exception):
            raise self._outcome

    def managed_accounts(self) -> list[str]:
        assert isinstance(self._outcome, list)
        return self._outcome

    def disconnect(self) -> None:
        self.disconnects += 1
        if self._disconnect_error is not None:
            raise self._disconnect_error


def _check(client: FakeClient):
    return module.check_gateway(client, host="127.0.0.1", port=4002, client_id=901)


def test_a_gateway_that_reports_an_account_is_alive() -> None:
    client = FakeClient(["DU1234567"])

    assert _check(client) == (module.GatewayState.ALIVE, "")
    assert client.connected_with == ("127.0.0.1", 4002, 901)
    assert client.disconnects == 1


def test_a_refused_connection_is_unreachable() -> None:
    client = FakeClient(ConnectionRefusedError("[Errno 111] Connection refused"))

    state, detail = _check(client)

    assert state is module.GatewayState.UNREACHABLE
    assert "ConnectionRefusedError" in detail
    assert "Connection refused" in detail
    assert client.disconnects == 1


def test_a_connection_with_no_account_is_rejected() -> None:
    state, detail = _check(FakeClient([]))

    assert state is module.GatewayState.REJECTED
    assert "no account" in detail


def test_a_runtime_error_from_the_client_is_rejected() -> None:
    state, detail = _check(FakeClient(RuntimeError("native handshake failed")))

    assert state is module.GatewayState.REJECTED
    assert detail == "RuntimeError: native handshake failed"


def test_an_unexpected_exception_is_a_failed_state_not_a_crash() -> None:
    state, detail = _check(FakeClient(KeyError("clientId")))

    assert state is module.GatewayState.REJECTED
    assert detail.startswith("KeyError")


def test_a_timeout_is_unreachable_and_names_the_exception() -> None:
    state, detail = _check(FakeClient(TimeoutError("startup sync")))

    assert state is module.GatewayState.UNREACHABLE
    assert detail == "TimeoutError: startup sync"


def test_a_failing_disconnect_does_not_change_the_state() -> None:
    client = FakeClient(["DU1234567"], disconnect_error=OSError("broken pipe"))

    assert _check(client) == (module.GatewayState.ALIVE, "")


def run_scripted(outcomes: list[tuple[object, str]], *, grace_seconds: float = 0.0, interval_seconds: float = 300.0):
    """Run the loop over scripted check results; return the alerts it raised."""
    script = list(outcomes)
    alerts: list[tuple[object, str]] = []
    sleeps: list[float] = []
    now = [0.0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds
        if len(sleeps) == len(outcomes):
            raise StopLoop

    with pytest.raises(StopLoop):
        module.run_health_check(
            lambda: script.pop(0),
            interval_seconds=interval_seconds,
            grace_seconds=grace_seconds,
            notify=lambda state, detail: alerts.append((state, detail)),
            sleep=sleep,
            clock=lambda: now[0],
        )
    assert sleeps == [interval_seconds] * len(outcomes)
    return alerts


ALIVE = (module.GatewayState.ALIVE, "")
DOWN = (module.GatewayState.UNREACHABLE, "refused")
LOGGED_OUT = (module.GatewayState.REJECTED, "no account")


def test_a_healthy_start_sends_no_alert() -> None:
    assert run_scripted([ALIVE, ALIVE, ALIVE]) == []


def test_a_start_with_the_gateway_down_alerts() -> None:
    assert run_scripted([DOWN]) == [DOWN]


def test_alerts_once_when_lost_and_once_when_recovered() -> None:
    assert run_scripted([ALIVE, DOWN, DOWN, DOWN, ALIVE]) == [DOWN, ALIVE]


def test_a_move_between_failure_states_alerts_again() -> None:
    assert run_scripted([DOWN, LOGGED_OUT]) == [DOWN, LOGGED_OUT]


def test_the_grace_clock_survives_a_change_between_failure_states() -> None:
    # Checks at 0, 300 and 600 s; the third fails differently, 600 s after the first failure.
    alerts = run_scripted([DOWN, DOWN, LOGGED_OUT], grace_seconds=600.0)

    assert alerts == [LOGGED_OUT]


def test_an_outage_shorter_than_the_grace_period_sends_nothing() -> None:
    # Checks at 0, 300 and 600 s fail; the Gateway is back at 900 s, inside a 1000 s grace.
    assert run_scripted([ALIVE, DOWN, DOWN, DOWN, ALIVE], grace_seconds=1000.0) == []


def test_a_failure_alerts_once_it_has_lasted_the_grace_period() -> None:
    # The first failing check is at 300 s; the one at 900 s is 600 s later.
    alerts = run_scripted([ALIVE, DOWN, DOWN, DOWN, ALIVE], grace_seconds=600.0)

    assert alerts == [DOWN, ALIVE]


def test_a_start_with_the_gateway_down_alerts_after_the_grace_period() -> None:
    assert run_scripted([DOWN, DOWN, DOWN], grace_seconds=600.0) == [DOWN]


def test_a_recovery_inside_the_grace_period_clears_the_clock() -> None:
    # Two short outages, each shorter than the grace period, must not add up.
    outcomes = [DOWN, ALIVE, DOWN, ALIVE, DOWN, ALIVE]

    assert run_scripted(outcomes, grace_seconds=400.0) == []


def test_logs_every_state_change_even_inside_the_grace_period(caplog) -> None:
    with caplog.at_level(logging.INFO, logger=HEALTH_MODULE):
        run_scripted([ALIVE, ALIVE, DOWN, DOWN, ALIVE], grace_seconds=10_000.0)

    assert [(record.levelno, record.getMessage()) for record in caplog.records] == [
        (logging.INFO, "IB Gateway alive"),
        (logging.WARNING, "IB Gateway unreachable: refused"),
        (logging.INFO, "IB Gateway alive"),
    ]


def test_send_state_alert_tells_the_operator_what_to_do(monkeypatch) -> None:
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(module, "notify_runtime_event", lambda **kwargs: sent.append(kwargs) or True)

    module.send_state_alert(
        module.GatewayState.REJECTED, "no account", webhook_url="https://example.test/hook", email_config=None
    )
    module.send_state_alert(module.GatewayState.UNREACHABLE, "refused", webhook_url=None, email_config=None)
    module.send_state_alert(module.GatewayState.ALIVE, "", webhook_url=None, email_config=None)

    assert [(call["status"], call["message"]) for call in sent] == [
        ("fail", "IB Gateway rejected: no account. Log in at IB Gateway."),
        ("fail", "IB Gateway unreachable: refused. Start IB Gateway and log in."),
        ("ok", "IB Gateway alive again"),
    ]
    assert sent[0]["webhook_url"] == "https://example.test/hook"
    assert {call["event"] for call in sent} == {"ibkr-gateway-health"}


def test_a_non_positive_interval_is_refused() -> None:
    with pytest.raises(SystemExit):
        module.parse_args(["--interval-seconds", "0"])


def test_a_negative_grace_period_is_refused() -> None:
    with pytest.raises(SystemExit):
        module.parse_args(["--grace-seconds", "-1"])
