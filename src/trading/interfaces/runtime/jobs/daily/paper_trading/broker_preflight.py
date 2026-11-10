"""Find the run accounts that cannot trade today, before the daily run submits anything.

``check_broker_sessions`` runs first. It connects every run account through ``get_broker_for_account``
and disconnects. Simulator accounts connect for free. The broker guard errors propagate untouched
(``LiveTradingNotEnabledError``, ``PaperBrokerAccountMismatchError``, ``UnknownBrokerTypeError``): they
mean the operator must investigate, not retry, so they stop the whole run, as does
``IbWebAccountUnavailableError`` (a wrong ``account_id`` is a configuration error, not an outage). A down
gateway or TWS/IB Gateway socket is unavailable, not an error. When no account has a usable session the
check raises ``BrokerSessionUnavailableError`` and the run fails before any step runs.

``check_broker_cash`` runs after the pre-trade reconcile has posted outstanding fills, so an unposted
fill cannot read as a shortfall.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from contextlib import suppress

import httpx

from infrastructure.brokers.factory import (
    LiveTradingNotEnabledError,
    PaperBrokerAccountMismatchError,
    UnknownBrokerTypeError,
    get_broker_for_account,
)
from infrastructure.brokers.ibkr_web.client import IbWebAccountUnavailableError
from infrastructure.database.connection import db_session
from trading.domain.broker_cash import broker_cash_shortfall
from trading.models import AccountRecord
from trading.services.accounts.mutations import get_account
from trading.services.operations.broker_cash import (
    account_cash_pool,
    fetch_book_cash_by_pool,
    fetch_pool_mates_outside_run,
)

__all__ = [
    "BrokerCashShortfallError",
    "BrokerSessionUnavailableError",
    "NoAccountCanTradeError",
    "check_broker_cash",
    "check_broker_sessions",
    "pool_mates_outside_run",
]

# The account-summary key that holds the broker's cash balance.
_CASH_KEY = "TotalCashValue"


class NoAccountCanTradeError(RuntimeError):
    """Every run account was left out before trading; ``skipped`` maps each to why."""

    def __init__(self, message: str, skipped: dict[str, str]) -> None:
        self.skipped = skipped
        super().__init__(message)


class BrokerSessionUnavailableError(NoAccountCanTradeError):
    """No run account has a usable broker session."""

    def __init__(self, unavailable: dict[str, str]) -> None:
        self.unavailable = unavailable
        super().__init__(
            "Broker session unavailable for every run account, no step ran. "
            + "; ".join(f"{name} ({reason})" for name, reason in unavailable.items())
            + ". Start the IBKR Client Portal gateway and log in, then re-run (a plain re-run works only if no run "
            "completed today). See docs/runbooks/ibkr-paper-trading.md (Gateway session).",
            unavailable,
        )


class BrokerCashShortfallError(NoAccountCanTradeError):
    """Every run account was left out by the cash check: its books hold more than the broker, or its cash was unreadable."""

    def __init__(self, skipped: dict[str, str]) -> None:
        super().__init__(
            "No run account can trade today, nothing was submitted. "
            + "; ".join(f"{name} ({reason})" for name, reason in skipped.items())
            + ". Fix each reason (bring the books' cash back in line with the broker's, or check the gateway "
            "session and the broker's ledger), then re-run (a plain re-run works only if no run completed today). "
            "See docs/runbooks/ibkr-paper-trading.md (Books hold more cash than the broker).",
            skipped,
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


def _reported_cash(account: AccountRecord) -> float | None:
    """The cash balance the broker reports for *account*, or None when its broker keeps no cash.

    Raises ``RuntimeError`` for an answer that carries no usable figure.
    """
    broker = get_broker_for_account(account)
    try:
        info = broker.get_account_info()
    except NotImplementedError:
        return None
    finally:
        with suppress(OSError, RuntimeError):
            broker.disconnect()
    cash = info.get(_CASH_KEY)
    if not isinstance(cash, (int, float)) or not math.isfinite(cash):
        raise RuntimeError(f"the broker's account summary has no usable {_CASH_KEY}")
    return cash


def check_broker_cash(account_names: list[str], *, already_skipped: Mapping[str, str]) -> dict[str, str]:
    """Map each account that cannot trade on its broker's cash to the reason.

    Accounts that reach one broker account share its cash, so every book of every account in the
    pool is counted, run or not. An account is mapped when the books hold more than the broker, and
    every account of a pool whose broker cash cannot be read is mapped too. Simulator accounts are
    not checked. Raises ``BrokerCashShortfallError`` when this, with *already_skipped*, leaves no
    account to trade. The broker guard errors propagate untouched.
    """
    pools: dict[str, list[AccountRecord]] = {}
    with db_session() as conn:
        book_cash = fetch_book_cash_by_pool(conn)
        for name in account_names:
            account = get_account(conn, name)
            pool = account_cash_pool(account)
            if pool is not None:
                pools.setdefault(pool, []).append(account)

    skipped: dict[str, str] = {}
    for pool, accounts in pools.items():
        try:
            cash = _reported_cash(accounts[0])
        except (
            LiveTradingNotEnabledError,
            PaperBrokerAccountMismatchError,
            UnknownBrokerTypeError,
            IbWebAccountUnavailableError,
        ):
            raise
        except (httpx.TransportError, OSError, RuntimeError, ValueError, ArithmeticError) as exc:
            skipped.update({account.name: f"could not read the broker's cash: {exc}" for account in accounts})
            continue
        if cash is not None and broker_cash_shortfall(book_cash[pool], cash):
            reason = f"the books hold {book_cash[pool]:.2f} cash and the broker holds {cash:.2f}"
            skipped.update({account.name: reason for account in accounts})
    if skipped and set(skipped) >= set(account_names):
        raise BrokerCashShortfallError({**already_skipped, **skipped})
    return skipped


def pool_mates_outside_run(account_names: list[str]) -> list[str]:
    """The accounts that share a broker cash pool with a run account but are not in the run."""
    with db_session() as conn:
        return fetch_pool_mates_outside_run(conn, account_names)
