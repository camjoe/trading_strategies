from __future__ import annotations

from tests.support.account_records import make_account_record


def make_accounts_service_row(
    *,
    id: int = 1,
    name: str = "acct",
    descriptive_name: str = "Account",
    initial_cash: float = 5000.0,
    benchmark_ticker: str = "SPY",
    created_at: str = "2026-01-01T00:00:00",
):
    """Account row for listing/display tests (final 0008 shape — settings and
    goals live on the default book; see ``make_book_record``)."""
    return make_account_record(
        id=id,
        name=name,
        descriptive_name=descriptive_name,
        initial_cash=initial_cash,
        created_at=created_at,
        benchmark_ticker=benchmark_ticker,
    )


__all__ = [
    "make_accounts_service_row",
]
