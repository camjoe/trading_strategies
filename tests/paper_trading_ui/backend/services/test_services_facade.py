from __future__ import annotations

from paper_trading_ui.backend import services


def test_services_facade_exports_expected_symbols() -> None:
    for symbol in services.__all__:
        assert hasattr(services, symbol), f"Missing export: {symbol}"
