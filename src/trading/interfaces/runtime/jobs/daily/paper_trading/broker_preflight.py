"""Fail the daily run before it changes anything when a broker session is unavailable.

Connects every run account through ``get_broker_for_account`` and disconnects.
Simulator accounts connect for free. The broker guard errors propagate untouched
(``LiveTradingNotEnabledError``, ``PaperBrokerAccountMismatchError``,
``UnknownBrokerTypeError``): they mean the operator must investigate, not retry.
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

__all__ = ["BrokerSessionUnavailableError", "check_broker_sessions"]


class BrokerSessionUnavailableError(RuntimeError):
    """A broker session could not be opened for one or more run accounts."""


def check_broker_sessions(account_names: list[str]) -> None:
    unavailable: list[str] = []
    with db_session() as conn:
        for name in account_names:
            account = get_account(conn, name)
            try:
                get_broker_for_account(account).disconnect()
            except LiveTradingNotEnabledError, PaperBrokerAccountMismatchError, UnknownBrokerTypeError:
                raise
            except (httpx.TransportError, RuntimeError) as exc:
                unavailable.append(f"{name} ({account.broker_type}): {exc}")
    if unavailable:
        raise BrokerSessionUnavailableError(
            "Broker session unavailable, no step ran. "
            + "; ".join(unavailable)
            + ". Start the IBKR Client Portal gateway and log in, then re-run. "
            "See docs/runbooks/ibkr-paper-trading.md (Gateway session)."
        )
