"""Shared runtime notification helpers."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any, Callable, TypedDict

from common.time import utc_now_iso

# Seconds to wait for a webhook response before treating the notification as failed.
WEBHOOK_TIMEOUT_SECONDS = 10.0

# User-Agent header for outbound runtime notification requests.
WEBHOOK_USER_AGENT = "trading-strategies-runtime-alert/1.0"


class RuntimeNotificationPayload(TypedDict):
    event: str
    status: str
    message: str
    sent_at: str
    details: dict[str, object]


def build_runtime_notification_payload(
    *,
    event: str,
    status: str,
    message: str,
    details: dict[str, object] | None = None,
) -> RuntimeNotificationPayload:
    return {
        "event": event,
        "status": status,
        "message": message,
        "sent_at": utc_now_iso(),
        "details": details or {},
    }


def send_webhook_notification(
    webhook_url: str,
    payload: RuntimeNotificationPayload,
    *,
    urlopen_fn: Callable[..., Any] = urllib.request.urlopen,
) -> None:
    normalized_url = webhook_url.strip()
    if not normalized_url:
        raise ValueError("Webhook URL must not be blank.")

    request = urllib.request.Request(
        normalized_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": WEBHOOK_USER_AGENT,
        },
        method="POST",
    )
    with urlopen_fn(request, timeout=WEBHOOK_TIMEOUT_SECONDS) as response:
        status_code = response.getcode()
    if status_code >= 400:
        raise RuntimeError(f"Webhook returned HTTP {status_code}.")


def notify_webhook_best_effort(
    *,
    webhook_url: str | None,
    event: str,
    status: str,
    message: str,
    details: dict[str, object] | None = None,
    urlopen_fn: Callable[..., Any] = urllib.request.urlopen,
) -> bool:
    if webhook_url is None or not webhook_url.strip():
        return False

    payload = build_runtime_notification_payload(
        event=event,
        status=status,
        message=message,
        details=details,
    )
    try:
        send_webhook_notification(webhook_url, payload, urlopen_fn=urlopen_fn)
    except (OSError, RuntimeError, TimeoutError, urllib.error.URLError, ValueError) as exc:
        print(
            f"[WARN] Failed to send runtime notification for {event}: {exc}",
            file=sys.stderr,
        )
        return False
    return True
