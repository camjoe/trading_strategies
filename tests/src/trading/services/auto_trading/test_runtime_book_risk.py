from __future__ import annotations

from types import SimpleNamespace

from trading.services.auto_trading.runtime_book_risk import compute_current_exposure_snapshot


def test_compute_current_exposure_snapshot_uses_injected_symbol_sector_map() -> None:
    positions = [
        SimpleNamespace(symbol="AAPL", market_value=300.0),
        SimpleNamespace(symbol="MSFT", market_value=200.0),
        SimpleNamespace(symbol="JPM", market_value=100.0),
    ]
    books = [SimpleNamespace(current_equity=1_000.0)]

    gross, net, max_symbol_pct, max_sector_pct = compute_current_exposure_snapshot(
        object(),
        account_id=1,
        fetch_positions_for_account_fn=lambda *_args, **_kwargs: positions,
        fetch_books_for_account_fn=lambda *_args, **_kwargs: books,
        symbol_sector_map={"AAPL": "technology", "MSFT": "technology", "JPM": "financials"},
    )

    assert gross == 600.0
    assert net == 600.0
    assert max_symbol_pct == 0.3
    assert max_sector_pct == 0.5
