"""Find the run accounts whose broker session is unavailable, before the daily run changes anything.

Connects every run account through ``get_broker_for_account`` and disconnects. Simulator accounts
connect for free. The broker guard errors propagate untouched (``LiveTradingNotEnabledError``,
``PaperBrokerAccountMismatchError``, ``UnknownBrokerTypeError``): they mean the operator must
investigate, not retry, so they stop the whole run.
"""

from __future__ import annotations

import httpx

from infrastructure.brokers.factory import (
    LiveTradingNotEnabledError,
    PaperBrokerAccountMismatchError,
    UnknownBrokerTypeError,
    get_broker_for_account,
)
from infrastructure.database.connection import db_session
from trading.services.accounts.mutations import get_account

__all__ = ["BrokerSessionUnavailableError", "check_broker_sessions", "unavailable_message"]


class BrokerSessionUnavailableError(RuntimeError):
    """No run account has a usable broker session."""


def check_broker_sessions(account_names: list[str]) -> dict[str, str]:
    """Map each account whose broker session is unavailable to ``"<broker type>: <reason>"``."""
    unavailable: dict[str, str] = {}
    with db_session() as conn:
        for name in account_names:
            account = get_account(conn, name)
            try:
                get_broker_for_account(account).disconnect()
            except LiveTradingNotEnabledError, PaperBrokerAccountMismatchError, UnknownBrokerTypeError:
                raise
            except (httpx.TransportError, RuntimeError) as exc:
                unavailable[name] = f"{account.broker_type}: {exc}"
    return unavailable


def unavailable_message(unavailable: dict[str, str]) -> str:
    """The failure text for a run in which every account is unavailable."""
    return (
        "Broker session unavailable for every run account, no step ran. "
        + "; ".join(f"{name} ({reason})" for name, reason in unavailable.items())
        + ". Start the IBKR Client Portal gateway and log in, then re-run. "
        "See docs/runbooks/ibkr-paper-trading.md (Gateway session)."
    )
