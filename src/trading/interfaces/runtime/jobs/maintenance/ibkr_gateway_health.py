"""Watch that IB Gateway is up and logged in, and alert when that changes.

Long-running worker, run as a service rather than from a scheduler:

    python -m trading.interfaces.runtime.jobs.maintenance.ibkr_gateway_health --port 4002

Every ``--interval-seconds`` it connects to the Gateway's API port, reads the managed accounts, and
disconnects. It uses its own ``--client-id`` so it never takes the id a trading session holds. It
cannot log in, and it cannot tell a stopped Gateway from one waiting at its login screen: both
refuse the connection, and either needs the operator. A connection that is accepted but times out is
also reported as unreachable; the detail names the exception.

A failure sends a runtime alert through the webhook and SMTP settings in the environment only once it
has lasted ``--grace-seconds``, so the Gateway's own nightly restart passes without one; the recovery
that follows an alert sends another. A healthy start sends nothing; a start with the Gateway still down
after the grace period alerts, which is the reminder to log in. Every change of state is logged at once.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from collections.abc import Callable
from enum import StrEnum

from common.logging_setup import configure_logging
from infrastructure.brokers.ibkr_socket.factory import build_ibkr_socket_client
from infrastructure.brokers.ibkr_socket.protocol import IbkrSocketClient
from trading.interfaces.runtime.jobs.job_helpers import RUNTIME_ALERT_WEBHOOK_ENV, resolve_email_config_from_env
from trading.interfaces.runtime.notifications import EmailNotificationConfig, notify_runtime_event

__all__ = ["GatewayState", "check_gateway", "main", "run_health_check", "send_state_alert"]

ALERT_EVENT = "ibkr-gateway-health"

# Distinct from the account rows' broker_client_id and from the default (1), so a check never
# collides with a trading session or an operator tool.
DEFAULT_CLIENT_ID = 901

# IB Gateway paper's API port.
DEFAULT_PORT = 4002

DEFAULT_INTERVAL_SECONDS = 300.0

# Long enough for IB Gateway's scheduled restart to finish without an alert.
DEFAULT_GRACE_SECONDS = 900.0

logger = logging.getLogger(__name__)


class GatewayState(StrEnum):
    ALIVE = "alive"
    REJECTED = "rejected"
    UNREACHABLE = "unreachable"


_REMEDY = {
    GatewayState.REJECTED: "Log in at IB Gateway.",
    GatewayState.UNREACHABLE: "Start IB Gateway and log in.",
}


def check_gateway(client: IbkrSocketClient, *, host: str, port: int, client_id: int) -> tuple[GatewayState, str]:
    """Connect, confirm the Gateway reports at least one account, and disconnect."""
    try:
        client.connect(host, port, client_id=client_id)
        accounts = client.managed_accounts()
    except OSError as exc:
        return GatewayState.UNREACHABLE, f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        # Anything else must not end the worker: a restart resets the grace period, so a
        # persistent error would never alert.
        return GatewayState.REJECTED, f"{type(exc).__name__}: {exc}"
    finally:
        try:
            client.disconnect()
        except Exception:
            logger.warning("Disconnecting the IB Gateway health check failed.", exc_info=True)
    if not accounts:
        return GatewayState.REJECTED, "connected, but IBKR reported no account"
    return GatewayState.ALIVE, ""


def send_state_alert(
    state: GatewayState,
    detail: str,
    *,
    webhook_url: str | None,
    email_config: EmailNotificationConfig | None,
) -> None:
    recovered = state is GatewayState.ALIVE
    notify_runtime_event(
        event=ALERT_EVENT,
        status="ok" if recovered else "fail",
        message="IB Gateway alive again" if recovered else f"IB Gateway {state.value}: {detail}. {_REMEDY[state]}",
        details={"state": state.value},
        webhook_url=webhook_url,
        email_config=email_config,
    )


def run_health_check(
    check: Callable[[], tuple[GatewayState, str]],
    *,
    interval_seconds: float,
    grace_seconds: float,
    notify: Callable[[GatewayState, str], None],
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    logged: GatewayState | None = None
    failing_since: float | None = None
    alerted: GatewayState | None = None
    while True:
        state, detail = check()
        if state != logged:
            level = logging.INFO if state is GatewayState.ALIVE else logging.WARNING
            logger.log(level, "IB Gateway %s%s", state.value, f": {detail}" if detail else "")
            logged = state
        if state is GatewayState.ALIVE:
            failing_since = None
            if alerted is not None:
                notify(state, detail)
                alerted = None
        else:
            now = clock()
            if failing_since is None:
                failing_since = now
            if now - failing_since >= grace_seconds and state != alerted:
                notify(state, detail)
                alerted = state
        sleep(interval_seconds)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alert when IB Gateway is down or logged out.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--client-id", type=int, default=DEFAULT_CLIENT_ID)
    parser.add_argument("--interval-seconds", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--grace-seconds", type=float, default=DEFAULT_GRACE_SECONDS)
    args = parser.parse_args(argv)
    if args.interval_seconds <= 0:
        parser.error("--interval-seconds must be positive")
    if args.grace_seconds < 0:
        parser.error("--grace-seconds must not be negative")
    return args


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    args = parse_args(argv)
    webhook_url = os.environ.get(RUNTIME_ALERT_WEBHOOK_ENV, "")
    email_config = resolve_email_config_from_env()
    run_health_check(
        lambda: check_gateway(build_ibkr_socket_client(), host=args.host, port=args.port, client_id=args.client_id),
        interval_seconds=args.interval_seconds,
        grace_seconds=args.grace_seconds,
        notify=lambda state, detail: send_state_alert(
            state, detail, webhook_url=webhook_url, email_config=email_config
        ),
    )


if __name__ == "__main__":
    main()
