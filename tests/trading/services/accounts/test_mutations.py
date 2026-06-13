import sqlite3

import pytest

from trading.models.account_config import AccountConfig
from trading.services.accounts import create_account


def test_create_account_rejects_unknown_strategy_name() -> None:
    with pytest.raises(ValueError, match="Unknown strategy 'mystery_strategy'"):
        create_account(
            sqlite3.connect(":memory:"),
            "acct",
            "mystery_strategy",
            5000.0,
            "SPY",
            config=AccountConfig(),
        )
