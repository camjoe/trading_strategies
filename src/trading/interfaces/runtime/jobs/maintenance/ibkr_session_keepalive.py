"""Hold the IBKR Client Portal session open between scheduled runs.

Long-running worker, run as a service rather than from a scheduler:

    python -m trading.interfaces.runtime.jobs.maintenance.ibkr_session_keepalive

The client's own keepalive thread lives only while a job is connected, so nothing
holds the session open between daily runs. This worker calls ``/tickle`` every
``keepalive_interval_seconds`` and logs each change of session state. It cannot
log in: a session that expired needs a manual login at the gateway.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from enum import StrEnum

import httpx

from common.logging_setup import configure_logging
from infrastructure.brokers.ibkr_web import InteractiveBrokersWebClient, load_ib_web_api_settings

__all__ = ["SessionState", "check_session", "main", "run_keepalive"]

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


def run_keepalive(
    client: InteractiveBrokersWebClient,
    *,
    interval_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    previous: SessionState | None = None
    while True:
        state, detail = check_session(client)
        if state != previous:
            level = logging.INFO if state is SessionState.ALIVE else logging.WARNING
            logger.log(level, "IBKR session %s%s", state.value, f": {detail}" if detail else "")
            previous = state
        sleep(interval_seconds)


def main() -> None:
    configure_logging()
    settings = load_ib_web_api_settings()
    client = InteractiveBrokersWebClient(settings=settings)
    try:
        run_keepalive(client, interval_seconds=settings.keepalive_interval_seconds)
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
