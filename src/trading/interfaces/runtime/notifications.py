"""Shared runtime notification helpers."""

from __future__ import annotations

import json
import smtplib
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, TypedDict

from common.time import utc_now_iso

# Seconds to wait for a webhook response before treating the notification as failed.
WEBHOOK_TIMEOUT_SECONDS = 10.0

# User-Agent header for outbound runtime notification requests.
WEBHOOK_USER_AGENT = "trading-strategies-runtime-alert/1.0"

# Seconds to wait for the SMTP server before treating an email notification as failed.
SMTP_TIMEOUT_SECONDS = 15.0

# Factory that opens an SMTP connection; injectable so tests supply a fake server.
SmtpFactory = Callable[..., smtplib.SMTP]


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


@dataclass(frozen=True)
class EmailNotificationConfig:
    """SMTP delivery settings for runtime email notifications (Plan P8, D8).

    Sourced from environment variables at the job boundary (see
    ``resolve_email_config_from_env``). Auth is optional: leave ``username``/
    ``password`` unset to relay through a server that does not require login.
    """

    host: str
    port: int
    sender: str
    recipients: tuple[str, ...]
    username: str | None = None
    password: str | None = None
    use_tls: bool = True

    def is_deliverable(self) -> bool:
        """Whether enough is configured to attempt delivery (host + sender + a recipient)."""
        return bool(self.host.strip() and self.sender.strip() and self.recipients)


def _build_email_message(config: EmailNotificationConfig, payload: RuntimeNotificationPayload) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"[{payload['status'].upper()}] {payload['event']}: {payload['message']}"
    message["From"] = config.sender
    message["To"] = ", ".join(config.recipients)
    body = json.dumps(payload, indent=2, sort_keys=True)
    message.set_content(f"{payload['message']}\n\n{body}\n")
    return message


def send_email_notification(
    config: EmailNotificationConfig,
    payload: RuntimeNotificationPayload,
    *,
    smtp_factory: SmtpFactory = smtplib.SMTP,
) -> None:
    if not config.is_deliverable():
        raise ValueError("Email config must set host, sender, and at least one recipient.")

    message = _build_email_message(config, payload)
    with smtp_factory(config.host, config.port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
        if config.use_tls:
            smtp.starttls()
        if config.username and config.password:
            smtp.login(config.username, config.password)
        smtp.send_message(message)


def notify_email_best_effort(
    *,
    email_config: EmailNotificationConfig | None,
    event: str,
    status: str,
    message: str,
    details: dict[str, object] | None = None,
    smtp_factory: SmtpFactory = smtplib.SMTP,
) -> bool:
    if email_config is None or not email_config.is_deliverable():
        return False

    payload = build_runtime_notification_payload(
        event=event,
        status=status,
        message=message,
        details=details,
    )
    try:
        send_email_notification(email_config, payload, smtp_factory=smtp_factory)
    except (OSError, smtplib.SMTPException, TimeoutError, ValueError) as exc:
        print(
            f"[WARN] Failed to send runtime email notification for {event}: {exc}",
            file=sys.stderr,
        )
        return False
    return True


def notify_runtime_event(
    *,
    event: str,
    status: str,
    message: str,
    details: dict[str, object] | None = None,
    webhook_url: str | None = None,
    email_config: EmailNotificationConfig | None = None,
    urlopen_fn: Callable[..., Any] = urllib.request.urlopen,
    smtp_factory: SmtpFactory = smtplib.SMTP,
) -> bool:
    """Fan a runtime event out to every configured transport (webhook and/or email).

    The event-level seam runtime jobs call so they stay transport-agnostic: an
    unset/blank transport config skips that transport, and delivery failures are
    non-fatal (logged to stderr). Each transport is attempted independently so one
    failing does not suppress the other.

    Returns True if any transport delivered.
    """
    webhook_delivered = notify_webhook_best_effort(
        webhook_url=webhook_url,
        event=event,
        status=status,
        message=message,
        details=details,
        urlopen_fn=urlopen_fn,
    )
    email_delivered = notify_email_best_effort(
        email_config=email_config,
        event=event,
        status=status,
        message=message,
        details=details,
        smtp_factory=smtp_factory,
    )
    return webhook_delivered or email_delivered
