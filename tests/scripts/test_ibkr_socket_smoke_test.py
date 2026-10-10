from __future__ import annotations

import argparse
from io import StringIO

import pytest

from scripts import ibkr_socket_smoke_test
from trading.models.orders import BrokerOrder, OrderRequest, OrderStatus


class _FakeAdapter:
    def __init__(
        self,
        *,
        connect_error: Exception | None = None,
        read_error: Exception | None = None,
        accounts: list[str] | None = None,
        submitted_order_id: str = "77",
        report_submitted_order: bool = True,
        cancel_error: Exception | None = None,
    ) -> None:
        self.connect_error = connect_error
        self.read_error = read_error
        self.accounts = ["DU1234567"] if accounts is None else accounts
        self.submitted_order_id = submitted_order_id
        self.report_submitted_order = report_submitted_order
        self.cancel_error = cancel_error
        self.connected = False
        self.disconnected = False
        self.quoted: list[str] = []
        self.placed: list[OrderRequest] = []
        self.cancelled: list[str] = []
        self.extra_open_trades: list[BrokerOrder] = []

    def connect(self) -> None:
        if self.connect_error is not None:
            raise self.connect_error
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True

    def managed_accounts(self) -> list[str]:
        return list(self.accounts)

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
            ),
            *self.extra_open_trades,
        ]

    def place_order(self, order: OrderRequest) -> BrokerOrder:
        self.placed.append(order)
        placed = BrokerOrder.from_request(order)
        placed.broker_order_id = self.submitted_order_id
        placed.status = OrderStatus.SUBMITTED
        if self.submitted_order_id and self.report_submitted_order:
            self.extra_open_trades.append(
                BrokerOrder(
                    account_id=0,
                    ticker=order.ticker,
                    side=order.side,
                    qty=order.qty,
                    price=order.price,
                    broker_order_id=self.submitted_order_id,
                    status=OrderStatus.SUBMITTED,
                )
            )
        return placed

    def cancel_order(self, broker_order_id: str) -> None:
        if self.cancel_error is not None:
            raise self.cancel_error
        self.cancelled.append(broker_order_id)
        self.extra_open_trades = [
            trade for trade in self.extra_open_trades if str(trade.broker_order_id) != str(broker_order_id)
        ]

    def get_quotes(self, tickers: list[str]) -> dict[str, dict[str, float]]:
        self.quoted = list(tickers)
        return {ticker: {"last": 1.0} for ticker in tickers}


def _args(**overrides) -> argparse.Namespace:
    defaults = {
        "host": "127.0.0.1",
        "port": 7497,
        "client_id": 99,
        "quote_tickers": "",
        "paper_order_check": False,
        "paper_order_symbol": "",
        "paper_order_limit_price": None,
        "paper_order_qty": 1.0,
        "paper_order_side": "buy",
        "skip_paper_order_cancel": False,
    }
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


def test_paper_venue_verdict_passes_for_paper_accounts(monkeypatch) -> None:
    code, output = _run(monkeypatch, _FakeAdapter(accounts=["DU1234567", "DU7654321"]))

    assert code == 0
    assert "DU1234567, DU7654321" in output
    assert "paper venue        : ok" in output


def test_paper_venue_verdict_flags_a_live_account(monkeypatch) -> None:
    """The preview must mirror the factory guard, including the all-accounts rule."""
    code, output = _run(monkeypatch, _FakeAdapter(accounts=["DU1234567", "U7654321"]))

    # Read-only checks still succeed — the verdict is advisory, not a failure.
    assert code == 0
    assert "WOULD BE REFUSED" in output
    assert "U7654321" in output


def test_paper_venue_verdict_flags_an_empty_account_list(monkeypatch) -> None:
    _, output = _run(monkeypatch, _FakeAdapter(accounts=[]))

    assert "<none reported>" in output
    assert "WOULD BE REFUSED" in output


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


class TestPaperOrderCheck:
    """The round trip fill reconciliation depends on: submit, read back, cancel."""

    @staticmethod
    def _order_args(**overrides) -> dict:
        return {
            "paper_order_check": True,
            "paper_order_symbol": "aapl",
            "paper_order_limit_price": 1.0,
            **overrides,
        }

    def test_submits_reads_back_and_cancels(self, monkeypatch) -> None:
        adapter = _FakeAdapter()

        code, output = _run(monkeypatch, adapter, **self._order_args())

        assert code == 0
        assert len(adapter.placed) == 1
        placed = adapter.placed[0]
        assert (placed.ticker, placed.side, placed.qty, placed.price) == ("AAPL", "buy", 1.0, 1.0)
        assert "submitted        : id 77" in output
        assert "read back        : status submitted" in output
        assert adapter.cancelled == ["77"]
        assert "order no longer open" in output
        assert "order round trip exercised" in output

    def test_order_the_broker_never_reports_is_called_out(self, monkeypatch) -> None:
        """Reconciliation reads the same call, so this is the failure that matters."""
        adapter = _FakeAdapter(report_submitted_order=False)

        code, output = _run(monkeypatch, adapter, **self._order_args())

        assert "FAIL read back   : get_open_trades() never reported id 77" in output
        # The verdict has to follow the failure: an operator gating go-live on the
        # exit code must not be told PASS here.
        assert code == 1
        assert "PASS" not in output
        assert "could not be verified" in output

    def test_refuses_to_submit_against_a_live_account(self, monkeypatch) -> None:
        """Host and port are operator flags, so this could be aimed at a live gateway."""
        adapter = _FakeAdapter(accounts=["U1234567"])

        code, output = _run(monkeypatch, adapter, **self._order_args())

        assert code == 1
        assert adapter.placed == []
        assert "Refusing --paper-order-check" in output
        assert adapter.disconnected is True

    def test_refuses_to_submit_when_no_account_is_reported(self, monkeypatch) -> None:
        adapter = _FakeAdapter(accounts=[])

        code, output = _run(monkeypatch, adapter, **self._order_args())

        assert code == 1
        assert adapter.placed == []
        assert "Refusing --paper-order-check" in output

    def test_missing_broker_order_id_is_an_error(self, monkeypatch) -> None:
        adapter = _FakeAdapter(submitted_order_id="")

        code, output = _run(monkeypatch, adapter, **self._order_args())

        assert code == 1
        assert "no broker order id" in output

    def test_cancel_can_be_skipped_to_leave_the_order_resting(self, monkeypatch) -> None:
        adapter = _FakeAdapter()

        _, output = _run(monkeypatch, adapter, **self._order_args(skip_paper_order_cancel=True))

        assert adapter.cancelled == []
        assert "rests until the close" in output

    def test_cancel_failure_is_reported_not_raised(self, monkeypatch) -> None:
        """Outside market hours IBKR can hold an order where a cancel is rejected."""
        adapter = _FakeAdapter(cancel_error=RuntimeError("order not cancellable"))

        code, output = _run(monkeypatch, adapter, **self._order_args())

        assert code == 0
        assert "best-effort failed" in output
        assert "order not cancellable" in output

    def test_nothing_is_submitted_without_the_flag(self, monkeypatch) -> None:
        adapter = _FakeAdapter()

        code, output = _run(monkeypatch, adapter)

        assert code == 0
        assert adapter.placed == []
        assert "paper order" not in output


class TestPaperOrderArgValidation:
    @staticmethod
    def _args(**overrides) -> argparse.Namespace:
        complete = {
            "paper_order_check": True,
            "paper_order_symbol": "AAPL",
            "paper_order_limit_price": 1.0,
        }
        return _args(**{**complete, **overrides})

    def test_accepts_a_complete_request(self) -> None:
        ibkr_socket_smoke_test.validate_paper_order_args(self._args())

    def test_symbol_is_required(self) -> None:
        with pytest.raises(ValueError, match="--paper-order-symbol"):
            ibkr_socket_smoke_test.validate_paper_order_args(self._args(paper_order_symbol="  "))

    def test_limit_price_is_required(self) -> None:
        # No default price: the wrong one is the difference between an order
        # that rests where we can observe it and one that fills.
        with pytest.raises(ValueError, match="--paper-order-limit-price"):
            ibkr_socket_smoke_test.validate_paper_order_args(self._args(paper_order_limit_price=None))

    def test_limit_price_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="--paper-order-limit-price"):
            ibkr_socket_smoke_test.validate_paper_order_args(self._args(paper_order_limit_price=0.0))

    def test_quantity_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="--paper-order-qty"):
            ibkr_socket_smoke_test.validate_paper_order_args(self._args(paper_order_qty=0.0))

    def test_nothing_is_validated_without_the_flag(self) -> None:
        ibkr_socket_smoke_test.validate_paper_order_args(_args(paper_order_check=False))


def test_read_failure_still_disconnects(monkeypatch) -> None:
    adapter = _FakeAdapter(read_error=RuntimeError("no market data permissions"))

    code, output = _run(monkeypatch, adapter)

    assert code == 1
    assert "FAIL read" in output
    assert "no market data permissions" in output
    assert adapter.disconnected is True
