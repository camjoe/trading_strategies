from __future__ import annotations

from trading.models.broker_order import BrokerOrder

from tests.support.account_records import make_account_record


def make_broker_account(**kwargs):
    return make_account_record(**kwargs)


def make_broker_order(**kwargs) -> BrokerOrder:
    defaults = {
        "account_id": 1,
        "ticker": "AAPL",
        "side": "buy",
        "qty": 10.0,
        "price": 150.0,
    }
    defaults.update(kwargs)
    return BrokerOrder(**defaults)


__all__ = [
    "make_broker_account",
    "make_broker_order",
]
