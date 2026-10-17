"""Find the run accounts whose broker session is unavailable, before the daily run changes anything.

Connects every run account through ``get_broker_for_account`` and disconnects. Simulator accounts
connect for free. The broker guard errors propagate untouched (``LiveTradingNotEnabledError``,
``PaperBrokerAccountMismatchError``, ``UnknownBrokerTypeError``): they mean the operator must
investigate, not retry, so they stop the whole run, as does ``IbWebAccountUnavailableError`` (a wrong
``account_id`` is a configuration error, not an outage). A down gateway or TWS/IB Gateway socket is
unavailable, not an error. When no account has a usable session the check raises
``BrokerSessionUnavailableError`` and the run fails before any step runs.
"""

from __future__ import annotations

import httpx

from infrastructure.brokers.factory import (
    LiveTradingNotEnabledError,
    PaperBrokerAccountMismatchError,
    UnknownBrokerTypeError,
    get_broker_for_account,
)
from infrastructure.brokers.ibkr_web.client import IbWebAccountUnavailableError
from infrastructure.database.connection import db_session
from trading.services.accounts.mutations import get_account

__all__ = ["BrokerSessionUnavailableError", "check_broker_sessions"]


class BrokerSessionUnavailableError(RuntimeError):
    """No run account has a usable broker session."""

    def __init__(self, unavailable: dict[str, str]) -> None:
        self.unavailable = unavailable
        super().__init__(
            "Broker session unavailable for every run account, no step ran. "
            + "; ".join(f"{name} ({reason})" for name, reason in unavailable.items())
            + ". Start the IBKR gateway (Client Portal Gateway or IB Gateway) and log in, then re-run (a plain re-run works only if no run "
            "completed today). See docs/runbooks/ibkr-paper-trading.md (Gateway session)."
        )


def check_broker_sessions(account_names: list[str]) -> dict[str, str]:
    """Map each account whose broker session is unavailable to ``"<broker type>: <reason>"``.

    Raises ``BrokerSessionUnavailableError`` when no account has a usable session.
    """
    unavailable: dict[str, str] = {}
    with db_session() as conn:
        for name in account_names:
            account = get_account(conn, name)
            try:
                get_broker_for_account(account).disconnect()
            except (
                LiveTradingNotEnabledError,
                PaperBrokerAccountMismatchError,
                UnknownBrokerTypeError,
                IbWebAccountUnavailableError,
            ):
                raise
            except (httpx.TransportError, OSError, RuntimeError) as exc:
                unavailable[name] = f"{account.broker_type}: {exc}"
    if set(unavailable) >= set(account_names):
        raise BrokerSessionUnavailableError(unavailable)
    return unavailable
