from __future__ import annotations

import argparse
from io import StringIO

from scripts import ibkr_socket_smoke_test
from trading.models.orders.broker_order import BrokerOrder, OrderStatus


class _FakeAdapter:
    def __init__(self, *, connect_error: Exception | None = None, read_error: Exception | None = None) -> None:
        self.connect_error = connect_error
        self.read_error = read_error
        self.connected = False
        self.disconnected = False
        self.quoted: list[str] = []

    def connect(self) -> None:
        if self.connect_error is not None:
            raise self.connect_error
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True

    def get_account_info(self) -> dict[str, float]:
        if self.read_error is not None:
            raise self.read_error
        return {"NetLiquidation": 62000.0}

    def get_positions(self) -> dict[str, float]:
        return {"AAPL": 10.0}

    def get_open_trades(self) -> list[BrokerOrder]:
        return [
            BrokerOrder(
                account_id=0,
                ticker="MSFT",
                side="buy",
                qty=3.0,
                price=400.0,
                broker_order_id="7",
                status=OrderStatus.SUBMITTED,
            )
        ]

    def get_quotes(self, tickers: list[str]) -> dict[str, dict[str, float]]:
        self.quoted = list(tickers)
        return {ticker: {"last": 1.0} for ticker in tickers}


def _args(**overrides) -> argparse.Namespace:
    defaults = {"host": "127.0.0.1", "port": 7497, "client_id": 99, "quote_tickers": ""}
    return argparse.Namespace(**{**defaults, **overrides})


def _run(monkeypatch, adapter: _FakeAdapter, **overrides) -> tuple[int, str]:
    monkeypatch.setattr(ibkr_socket_smoke_test, "build_adapter", lambda *_a, **_k: adapter)
    out = StringIO()
    code = ibkr_socket_smoke_test.run_smoke_test(_args(**overrides), out=out)
    return code, out.getvalue()


def test_smoke_test_reports_read_only_results(monkeypatch) -> None:
    adapter = _FakeAdapter()

    code, output = _run(monkeypatch, adapter)

    assert code == 0
    assert adapter.connected is True
    assert adapter.disconnected is True
    assert "NetLiquidation" in output
    assert "1 symbol(s)" in output
    assert "MSFT buy qty=3.0" in output
    assert "PASS" in output


def test_quotes_are_requested_only_when_tickers_given(monkeypatch) -> None:
    adapter = _FakeAdapter()

    _run(monkeypatch, adapter, quote_tickers=" aapl , msft ")

    assert adapter.quoted == ["AAPL", "MSFT"]


def test_connect_failure_reports_actionable_hint(monkeypatch) -> None:
    adapter = _FakeAdapter(connect_error=ConnectionRefusedError("refused"))

    code, output = _run(monkeypatch, adapter)

    assert code == 1
    assert "FAIL connect" in output
    assert "TWS/IB Gateway running" in output
    # Nothing to tear down when the connection never came up.
    assert adapter.disconnected is False


def test_read_failure_still_disconnects(monkeypatch) -> None:
    adapter = _FakeAdapter(read_error=RuntimeError("no market data permissions"))

    code, output = _run(monkeypatch, adapter)

    assert code == 1
    assert "FAIL read" in output
    assert "no market data permissions" in output
    assert adapter.disconnected is True
