from __future__ import annotations

import pytest

from tests.src.trading.interfaces.runtime.jobs.loaders import check_daily_trader_health as health_module


@pytest.fixture
def fresh_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the trader health check's account freshness result OK without opening a database."""
    monkeypatch.setattr(
        health_module,
        "_check_freshness",
        lambda _args: {"status": "ok", "message": "Every account has a recent equity snapshot", "accounts": []},
    )
