from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.support.repositories import insert_repository_account
from tests.support.sleeves import insert_test_sleeve


@pytest.fixture
def report_env(conn) -> SimpleNamespace:
    """Account + sleeve ready for daily-report tests."""
    account_name = "report_acct"
    account_id = insert_repository_account(conn, name=account_name)
    sleeve_id = insert_test_sleeve(
        conn,
        account_id=account_id,
        name="sleeve_a",
        start_equity=10_000.0,
        current_cash=10_000.0,
        current_equity=10_000.0,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    return SimpleNamespace(account_id=account_id, account_name=account_name, sleeve_id=sleeve_id)
