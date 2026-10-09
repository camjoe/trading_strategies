"""Hold the IBKR Client Portal session open between scheduled runs.

Long-running worker, run as a service rather than from a scheduler:

    python -m trading.interfaces.runtime.jobs.maintenance.ibkr_session_keepalive

The client's own keepalive thread lives only while a job is connected, so nothing
holds the session open between daily runs. This worker calls ``/tickle`` every
``keepalive_interval_seconds`` and logs each change of session state. It cannot
log in: a session that expired needs a manual login at the gateway.

Each change away from ``alive`` sends a runtime alert through the webhook and
SMTP settings in the environment, and so does the recovery that follows it. A
healthy start sends nothing.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from enum import StrEnum

import httpx

from common.logging_setup import configure_logging
from infrastructure.brokers.ibkr_web import InteractiveBrokersWebClient, load_ib_web_api_settings
from trading.interfaces.runtime.jobs.job_helpers import RUNTIME_ALERT_WEBHOOK_ENV, resolve_email_config_from_env
from trading.interfaces.runtime.notifications import EmailNotificationConfig, notify_runtime_event

__all__ = ["SessionState", "check_session", "main", "run_keepalive", "send_state_alert"]

ALERT_EVENT = "ibkr-session-keepalive"

logger = logging.getLogger(__name__)


class SessionState(StrEnum):
    ALIVE = "alive"
    REJECTED = "rejected"
    UNREACHABLE = "unreachable"


def check_session(client: InteractiveBrokersWebClient) -> tuple[SessionState, str]:
    """Tickle the gateway, then confirm the session is still authenticated."""
    try:
        client.tickle()
        client.validate_session()
    except httpx.TransportError as exc:
        return SessionState.UNREACHABLE, str(exc)
    except RuntimeError as exc:
        return SessionState.REJECTED, str(exc)
    return SessionState.ALIVE, ""


_REMEDY = {
    SessionState.REJECTED: "Log in at the Client Portal gateway.",
    SessionState.UNREACHABLE: "Start the Client Portal gateway and log in.",
}


def send_state_alert(
    state: SessionState,
    detail: str,
    *,
    webhook_url: str | None,
    email_config: EmailNotificationConfig | None,
) -> None:
    recovered = state is SessionState.ALIVE
    notify_runtime_event(
        event=ALERT_EVENT,
        status="ok" if recovered else "fail",
        message="IBKR session alive again" if recovered else f"IBKR session {state.value}: {detail}. {_REMEDY[state]}",
        details={"state": state.value},
        webhook_url=webhook_url,
        email_config=email_config,
    )


def run_keepalive(
    client: InteractiveBrokersWebClient,
    *,
    interval_seconds: float,
    notify: Callable[[SessionState, str], None],
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    previous: SessionState | None = None
    while True:
        state, detail = check_session(client)
        if state != previous:
            level = logging.INFO if state is SessionState.ALIVE else logging.WARNING
            logger.log(level, "IBKR session %s%s", state.value, f": {detail}" if detail else "")
            if state is not SessionState.ALIVE or previous is not None:
                notify(state, detail)
            previous = state
        sleep(interval_seconds)


def main() -> None:
    configure_logging()
    settings = load_ib_web_api_settings()
    client = InteractiveBrokersWebClient(settings=settings)
    webhook_url = os.environ.get(RUNTIME_ALERT_WEBHOOK_ENV, "")
    email_config = resolve_email_config_from_env()
    try:
        run_keepalive(
            client,
            interval_seconds=settings.keepalive_interval_seconds,
            notify=lambda state, detail: send_state_alert(
                state, detail, webhook_url=webhook_url, email_config=email_config
            ),
        )
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
