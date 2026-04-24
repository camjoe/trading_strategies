import sqlite3

import pytest

from trading.models.account_config import AccountConfig
from trading.services.accounts import create_account


def test_create_account_rejects_unknown_strategy_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from trading.services.accounts import mutations as account_mutations

    insert_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        account_mutations,
        "insert_account",
        lambda *args, **kwargs: insert_calls.append((args, kwargs)),
    )

    with pytest.raises(ValueError, match="Unknown strategy 'mystery_strategy'"):
        create_account(
            sqlite3.connect(":memory:"),
            "acct",
            "mystery_strategy",
            5000.0,
            "SPY",
            config=AccountConfig(),
        )

    assert insert_calls == []
