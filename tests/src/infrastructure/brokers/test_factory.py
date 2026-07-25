from unittest.mock import MagicMock, patch

import pytest

from infrastructure.brokers.factory import LiveTradingNotEnabledError, get_broker_for_account
from infrastructure.brokers.ibkr_web import IbWebApiSettings
from infrastructure.brokers.ibkr_web.adapter import InteractiveBrokersWebAdapter
from infrastructure.brokers.paper_adapter import PaperBrokerAdapter
from tests.support.brokers import make_broker_account


class TestGetBrokerForAccount:
    def test_paper_account_returns_paper_adapter(self):
        broker = get_broker_for_account(make_broker_account(broker_type="paper"))
        assert isinstance(broker, PaperBrokerAdapter)

    def test_missing_broker_type_defaults_to_paper(self):
        broker = get_broker_for_account(make_broker_account(broker_type=None))
        assert isinstance(broker, PaperBrokerAdapter)

    def test_ib_web_without_live_trading_enabled_raises(self):
        account = make_broker_account(broker_type="interactive_brokers_web", live_trading_enabled=0)
        with pytest.raises(LiveTradingNotEnabledError, match="live_trading_enabled"):
            get_broker_for_account(account)

    def test_ib_web_with_live_trading_enabled_connects(self):
        account = make_broker_account(broker_type="interactive_brokers_web")
        mock_client = MagicMock()
        with (
            patch("infrastructure.brokers.factory._require_live_trading_enabled"),
            patch(
                "infrastructure.brokers.factory.load_ib_web_api_settings",
                return_value=IbWebApiSettings(
                    base_url="https://example.test/v1/api",
                    account_id="U1234567",
                    headers={},
                ),
            ),
            patch("infrastructure.brokers.factory.InteractiveBrokersWebClient", return_value=mock_client),
        ):
            broker = get_broker_for_account(account)
        assert isinstance(broker, InteractiveBrokersWebAdapter)
        mock_client.connect.assert_called_once_with()


class TestLiveTradingSafety:
    def test_paper_adapter_never_requires_live_enabled(self):
        for flag in (0, None):
            broker = get_broker_for_account(make_broker_account(broker_type="paper", live_trading_enabled=flag))
            assert isinstance(broker, PaperBrokerAdapter)

    def test_live_trading_not_enabled_error_is_runtime_error(self):
        assert issubclass(LiveTradingNotEnabledError, RuntimeError)
