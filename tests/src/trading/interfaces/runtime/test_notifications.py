from __future__ import annotations

import json
import smtplib
import urllib.error
from types import SimpleNamespace

import pytest

from trading.interfaces.runtime.notifications import (
    WEBHOOK_TIMEOUT_SECONDS,
    EmailNotificationConfig,
    build_runtime_notification_payload,
    notify_email_best_effort,
    notify_runtime_event,
    notify_webhook_best_effort,
    send_email_notification,
    send_webhook_notification,
)


class _FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self._status_code = status_code

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def getcode(self) -> int:
        return self._status_code


def test_build_runtime_notification_payload_includes_expected_fields() -> None:
    payload = build_runtime_notification_payload(
        event="daily-trader-health",
        status="fail",
        message="Latest log is stale",
        details={"latest_log": "/tmp/log.txt"},
    )

    assert payload["event"] == "daily-trader-health"
    assert payload["status"] == "fail"
    assert payload["message"] == "Latest log is stale"
    assert payload["details"] == {"latest_log": "/tmp/log.txt"}
    assert payload["sent_at"]


def test_send_webhook_notification_posts_json_payload() -> None:
    captured = SimpleNamespace(request=None, timeout=None)

    def _fake_urlopen(request, timeout):
        captured.request = request
        captured.timeout = timeout
        return _FakeResponse(200)

    payload = build_runtime_notification_payload(
        event="daily-paper-trading",
        status="ok",
        message="Completed",
        details={"account_count": 2},
    )
    send_webhook_notification("https://example.test/webhook", payload, urlopen_fn=_fake_urlopen)

    assert captured.timeout == WEBHOOK_TIMEOUT_SECONDS
    assert captured.request.full_url == "https://example.test/webhook"
    assert captured.request.get_method() == "POST"
    assert captured.request.headers["Content-type"] == "application/json"
    assert json.loads(captured.request.data.decode("utf-8"))["message"] == "Completed"


def test_notify_webhook_best_effort_returns_false_and_warns_on_failure(capsys) -> None:
    def _fake_urlopen(request, timeout):
        raise urllib.error.URLError("boom")

    sent = notify_webhook_best_effort(
        webhook_url="https://example.test/webhook",
        event="daily-paper-trading",
        status="fail",
        message="Failed",
        urlopen_fn=_fake_urlopen,
    )

    assert sent is False
    assert "Failed to send runtime notification" in capsys.readouterr().err


def test_send_webhook_notification_rejects_blank_url() -> None:
    payload = build_runtime_notification_payload(
        event="daily-paper-trading",
        status="ok",
        message="Completed",
    )

    with pytest.raises(ValueError, match="must not be blank"):
        send_webhook_notification("   ", payload)


def test_send_webhook_notification_raises_for_http_error_status() -> None:
    payload = build_runtime_notification_payload(
        event="daily-paper-trading",
        status="fail",
        message="Broken",
    )

    with pytest.raises(RuntimeError, match="HTTP 500"):
        send_webhook_notification(
            "https://example.test/webhook", payload, urlopen_fn=lambda *_a, **_k: _FakeResponse(500)
        )


def test_notify_webhook_best_effort_returns_true_on_success() -> None:
    sent = notify_webhook_best_effort(
        webhook_url="https://example.test/webhook",
        event="daily-paper-trading",
        status="ok",
        message="Completed",
        urlopen_fn=lambda *_a, **_k: _FakeResponse(204),
    )

    assert sent is True


def test_notify_runtime_event_delivers_via_webhook_transport() -> None:
    sent = notify_runtime_event(
        event="daily-paper-trading",
        status="ok",
        message="Completed",
        details={"account_count": 2},
        webhook_url="https://example.test/webhook",
        urlopen_fn=lambda *_a, **_k: _FakeResponse(204),
    )

    assert sent is True


def test_notify_runtime_event_returns_false_without_transport_config() -> None:
    sent = notify_runtime_event(
        event="daily-paper-trading",
        status="fail",
        message="Failed",
        urlopen_fn=lambda *_a, **_k: pytest.fail("no transport configured; nothing should be sent"),
    )

    assert sent is False


class _FakeSMTP:
    def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args: tuple[str, str] | None = None
        self.sent_messages: list[object] = []

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def send_message(self, message: object) -> None:
        self.sent_messages.append(message)


def _capturing_smtp_factory(store: list[_FakeSMTP]):
    def factory(host: str, port: int, timeout: float | None = None) -> _FakeSMTP:
        smtp = _FakeSMTP(host, port, timeout=timeout)
        store.append(smtp)
        return smtp

    return factory


def _email_config(**overrides) -> EmailNotificationConfig:
    base = dict(host="smtp.test", port=587, sender="alerts@test", recipients=("ops@test",))
    base.update(overrides)
    return EmailNotificationConfig(**base)


def test_send_email_notification_sends_message_with_auth_and_tls() -> None:
    servers: list[_FakeSMTP] = []
    payload = build_runtime_notification_payload(event="daily-trader-health", status="fail", message="Stale log")

    send_email_notification(
        _email_config(username="user", password="secret"),
        payload,
        smtp_factory=_capturing_smtp_factory(servers),
    )

    assert len(servers) == 1
    server = servers[0]
    assert (server.host, server.port) == ("smtp.test", 587)
    assert server.started_tls is True
    assert server.login_args == ("user", "secret")
    assert len(server.sent_messages) == 1
    message = server.sent_messages[0]
    assert message["To"] == "ops@test"
    assert message["From"] == "alerts@test"
    assert "daily-trader-health" in message["Subject"]
    assert "Stale log" in message.get_content()


def test_send_email_notification_skips_login_without_credentials() -> None:
    servers: list[_FakeSMTP] = []
    payload = build_runtime_notification_payload(event="e", status="ok", message="m")

    send_email_notification(_email_config(), payload, smtp_factory=_capturing_smtp_factory(servers))

    assert servers[0].login_args is None
    assert servers[0].started_tls is True


def test_send_email_notification_skips_tls_when_disabled() -> None:
    servers: list[_FakeSMTP] = []
    payload = build_runtime_notification_payload(event="e", status="ok", message="m")

    send_email_notification(_email_config(use_tls=False), payload, smtp_factory=_capturing_smtp_factory(servers))

    assert servers[0].started_tls is False


def test_send_email_notification_rejects_non_deliverable_config() -> None:
    payload = build_runtime_notification_payload(event="e", status="ok", message="m")

    with pytest.raises(ValueError, match="host, sender"):
        send_email_notification(
            EmailNotificationConfig(host="", port=0, sender="", recipients=()),
            payload,
        )


def test_notify_email_best_effort_returns_false_without_config() -> None:
    assert notify_email_best_effort(email_config=None, event="e", status="ok", message="m") is False


def test_notify_email_best_effort_returns_false_and_warns_on_failure(capsys) -> None:
    def _boom_factory(host, port, timeout=None):
        raise smtplib.SMTPException("nope")

    sent = notify_email_best_effort(
        email_config=_email_config(),
        event="daily-trader-health",
        status="fail",
        message="Failed",
        smtp_factory=_boom_factory,
    )

    assert sent is False
    assert "Failed to send runtime email notification" in capsys.readouterr().err


def test_notify_email_best_effort_returns_true_on_success() -> None:
    servers: list[_FakeSMTP] = []
    sent = notify_email_best_effort(
        email_config=_email_config(),
        event="e",
        status="ok",
        message="m",
        smtp_factory=_capturing_smtp_factory(servers),
    )

    assert sent is True
    assert len(servers[0].sent_messages) == 1


def test_notify_runtime_event_fans_out_to_webhook_and_email() -> None:
    servers: list[_FakeSMTP] = []
    sent = notify_runtime_event(
        event="daily-paper-trading",
        status="ok",
        message="Completed",
        webhook_url="https://example.test/webhook",
        email_config=_email_config(),
        urlopen_fn=lambda *_a, **_k: _FakeResponse(204),
        smtp_factory=_capturing_smtp_factory(servers),
    )

    assert sent is True
    assert len(servers[0].sent_messages) == 1


def test_notify_runtime_event_delivers_via_email_only() -> None:
    servers: list[_FakeSMTP] = []
    sent = notify_runtime_event(
        event="daily-paper-trading",
        status="fail",
        message="Failed",
        email_config=_email_config(),
        smtp_factory=_capturing_smtp_factory(servers),
    )

    assert sent is True
    assert len(servers[0].sent_messages) == 1
