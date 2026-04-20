from __future__ import annotations

import json
import urllib.error
from types import SimpleNamespace

from trading.services.notifications_service import (
    WEBHOOK_TIMEOUT_SECONDS,
    build_runtime_notification_payload,
    notify_webhook_best_effort,
    send_webhook_notification,
)


class _FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self._status_code = status_code

    def __enter__(self) -> "_FakeResponse":
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
