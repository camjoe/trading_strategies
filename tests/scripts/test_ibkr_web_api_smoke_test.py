from __future__ import annotations

from io import StringIO

from scripts import ibkr_web_api_smoke_test
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
