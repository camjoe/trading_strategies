from __future__ import annotations

import argparse
from io import StringIO

import pytest

from scripts import ibkr_web_api_smoke_test
from trading.models.broker_order import BrokerOrder, OrderStatus
from trading.brokers.ib_web_client import IbWebApiSettings


class _FakeClient:
    def __init__(self) -> None:
        self.connected = False
        self.disconnected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True

    def fetch_ledger(self) -> dict[str, object]:
        return {
            "BASE": {
                "cashbalance": 50000.0,
                "netliquidationvalue": 62000.0,
            }
        }

    def fetch_summary(self) -> dict[str, object]:
        return {
            "buyingpower": {"amount": 100000.0},
            "netliquidation": {"amount": 62000.0},
        }

    def fetch_positions(self) -> list[dict[str, object]]:
        return [{"conid": 1}, {"conid": 2}]


def test_run_smoke_test_prints_sanitized_summary() -> None:
    client = _FakeClient()
    out = StringIO()

    ibkr_web_api_smoke_test.run_smoke_test(
        client,  # type: ignore[arg-type]
        account_id="U1234567",
        out=out,
    )

    output = out.getvalue()
    assert client.connected is True
    assert "U1****67" in output
    assert "U1234567" not in output
    assert "Cash balance (BASE): 50,000.00" in output
    assert "Positions loaded (2 row(s))" in output


def test_main_redacts_account_id_on_failure(monkeypatch, capsys) -> None:
    settings = IbWebApiSettings(
        base_url="https://localhost:5000/v1/api",
        account_id="U1234567",
        headers={},
    )

    class _FailingClient:
        def __init__(self, _settings: IbWebApiSettings) -> None:
            self._settings = _settings

        def connect(self) -> None:
            raise RuntimeError(
                "Configured IBKR Web API account_id 'U1234567' is not visible in the current session."
            )

        def disconnect(self) -> None:
            return None

    monkeypatch.setattr(ibkr_web_api_smoke_test, "load_ib_web_api_settings", lambda: settings)
    monkeypatch.setattr(ibkr_web_api_smoke_test, "InteractiveBrokersWebClient", _FailingClient)

    result = ibkr_web_api_smoke_test.main()

    assert result == 1
    captured = capsys.readouterr()
    assert "U1****67" in captured.err
    assert "U1234567" not in captured.err


def test_validate_paper_order_args_requires_symbol_and_limit_price() -> None:
    args = argparse.Namespace(
        paper_order_check=True,
        paper_order_symbol="",
        paper_order_qty=1.0,
        paper_order_limit_price=None,
    )

    with pytest.raises(ValueError, match="paper-order-symbol"):
        ibkr_web_api_smoke_test._validate_paper_order_args(args)

    args.paper_order_symbol = "AAPL"
    with pytest.raises(ValueError, match="paper-order-limit-price"):
        ibkr_web_api_smoke_test._validate_paper_order_args(args)


def test_run_paper_order_check_submits_and_cancels() -> None:
    out = StringIO()
    cancelled: list[str] = []

    class _FakeAdapter:
        def place_order(self, order: BrokerOrder) -> BrokerOrder:
            order.broker_order_id = "12345"
            order.status = OrderStatus.SUBMITTED
            return order

        def get_open_trades(self) -> list[BrokerOrder]:
            return [
                BrokerOrder(
                    account_id=0,
                    ticker="AAPL",
                    side="buy",
                    qty=1.0,
                    price=1.0,
                    broker_order_id="12345",
                    status=OrderStatus.SUBMITTED,
                )
            ]

        def cancel_order(self, broker_order_id: str) -> None:
            cancelled.append(broker_order_id)

    class _FakeClient:
        def fetch_orders(self) -> list[dict[str, object]]:
            return [{"orderId": "12345", "status": "Cancelled"}]

    ibkr_web_api_smoke_test.run_paper_order_check(
        client=_FakeClient(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        out=out,
        symbol="AAPL",
        qty=1.0,
        limit_price=1.0,
        side="buy",
        cancel_order=True,
    )

    output = out.getvalue()
    assert cancelled == ["12345"]
    assert "Paper order submitted" in output
    assert "Open-order lookup returned status submitted" in output
    assert "Broker-reported post-cancel status: Cancelled" in output


def test_main_runs_optional_paper_order_check(monkeypatch, capsys) -> None:
    settings = IbWebApiSettings(
        base_url="https://localhost:5000/v1/api",
        account_id="U1234567",
        headers={},
    )

    class _FakeClient:
        def __init__(self, _settings: IbWebApiSettings) -> None:
            self._settings = _settings

        def disconnect(self) -> None:
            return None

    smoke_calls: list[str] = []
    order_calls: list[str] = []

    monkeypatch.setattr(ibkr_web_api_smoke_test, "load_ib_web_api_settings", lambda: settings)
    monkeypatch.setattr(ibkr_web_api_smoke_test, "InteractiveBrokersWebClient", _FakeClient)
    monkeypatch.setattr(
        ibkr_web_api_smoke_test,
        "run_smoke_test",
        lambda client, *, account_id, out: smoke_calls.append(account_id),
    )
    monkeypatch.setattr(
        ibkr_web_api_smoke_test,
        "run_paper_order_check",
        lambda **kwargs: order_calls.append(kwargs["symbol"]),
    )
    monkeypatch.setattr(
        ibkr_web_api_smoke_test,
        "parse_args",
        lambda: argparse.Namespace(
            paper_order_check=True,
            paper_order_symbol="AAPL",
            paper_order_qty=1.0,
            paper_order_limit_price=1.0,
            paper_order_side="buy",
            skip_paper_order_cancel=False,
        ),
    )

    result = ibkr_web_api_smoke_test.main()

    assert result == 0
    assert smoke_calls == ["U1234567"]
    assert order_calls == ["AAPL"]
    assert capsys.readouterr().err == ""
