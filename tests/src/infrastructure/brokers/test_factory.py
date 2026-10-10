from unittest.mock import MagicMock, patch

import pytest

from infrastructure.brokers.factory import (
    LiveTradingNotEnabledError,
    PaperBrokerAccountMismatchError,
    UnknownBrokerTypeError,
    get_broker_for_account,
)
from infrastructure.brokers.ibkr_web import IbWebApiSettings
from infrastructure.brokers.ibkr_web.adapter import InteractiveBrokersWebAdapter
from infrastructure.brokers.paper_adapter import PaperBrokerAdapter
from tests.support.brokers import make_broker_account


def _web_api_settings(account_id: str) -> IbWebApiSettings:
    return IbWebApiSettings(
        base_url="https://example.test/v1/api",
        account_id=account_id,
        headers={},
    )


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
                return_value=_web_api_settings("U1234567"),
            ),
            patch("infrastructure.brokers.factory.InteractiveBrokersWebClient", return_value=mock_client),
        ):
            broker = get_broker_for_account(account)
        assert isinstance(broker, InteractiveBrokersWebAdapter)
        mock_client.connect.assert_called_once_with()


class TestIbkrPaperBrokerType:
    """`interactive_brokers_web_paper` trades real IBKR mechanics against a paper account.

    It skips the real-money guard and asserts the account instead — see
    docs/adr/017-ibkr-paper-broker-type.md.
    """

    def test_paper_account_id_connects_without_live_trading_enabled(self):
        account = make_broker_account(broker_type="interactive_brokers_web_paper", live_trading_enabled=0)
        mock_client = MagicMock()
        with (
            patch(
                "infrastructure.brokers.factory.load_ib_web_api_settings",
                return_value=_web_api_settings("DU1234567"),
            ),
            patch("infrastructure.brokers.factory.InteractiveBrokersWebClient", return_value=mock_client),
        ):
            broker = get_broker_for_account(account)
        assert isinstance(broker, InteractiveBrokersWebAdapter)
        mock_client.connect.assert_called_once_with()

    def test_live_account_id_is_refused(self):
        account = make_broker_account(broker_type="interactive_brokers_web_paper", live_trading_enabled=0)
        with (
            patch(
                "infrastructure.brokers.factory.load_ib_web_api_settings",
                return_value=_web_api_settings("U1234567"),
            ),
            patch("infrastructure.brokers.factory.InteractiveBrokersWebClient") as mock_client_cls,
            pytest.raises(PaperBrokerAccountMismatchError, match="not an IBKR paper account"),
        ):
            get_broker_for_account(account)
        mock_client_cls.assert_not_called()

    def test_live_account_id_is_refused_even_when_live_trading_enabled(self):
        """The flag must not buy a way past the paper-account assertion."""
        account = make_broker_account(broker_type="interactive_brokers_web_paper", live_trading_enabled=1)
        with (
            patch(
                "infrastructure.brokers.factory.load_ib_web_api_settings",
                return_value=_web_api_settings("U1234567"),
            ),
            pytest.raises(PaperBrokerAccountMismatchError),
        ):
            get_broker_for_account(account)

    def test_blank_account_id_is_refused(self):
        account = make_broker_account(broker_type="interactive_brokers_web_paper", live_trading_enabled=0)
        with (
            patch(
                "infrastructure.brokers.factory.load_ib_web_api_settings",
                return_value=_web_api_settings("   "),
            ),
            pytest.raises(PaperBrokerAccountMismatchError),
        ):
            get_broker_for_account(account)

    def test_account_id_prefix_match_is_case_insensitive(self):
        account = make_broker_account(broker_type="interactive_brokers_web_paper", live_trading_enabled=0)
        mock_client = MagicMock()
        with (
            patch(
                "infrastructure.brokers.factory.load_ib_web_api_settings",
                return_value=_web_api_settings("du1234567"),
            ),
            patch("infrastructure.brokers.factory.InteractiveBrokersWebClient", return_value=mock_client),
        ):
            broker = get_broker_for_account(account)
        assert isinstance(broker, InteractiveBrokersWebAdapter)

    def test_paper_account_id_does_not_unlock_the_live_web_path(self):
        """A DU account id must not let `interactive_brokers_web` skip the live guard."""
        account = make_broker_account(broker_type="interactive_brokers_web", live_trading_enabled=0)
        with (
            patch(
                "infrastructure.brokers.factory.load_ib_web_api_settings",
                return_value=_web_api_settings("DU1234567"),
            ),
            pytest.raises(LiveTradingNotEnabledError, match="live_trading_enabled"),
        ):
            get_broker_for_account(account)

    def test_paper_account_mismatch_error_is_runtime_error(self):
        assert issubclass(PaperBrokerAccountMismatchError, RuntimeError)


class TestIbkrSocketVenues:
    """Both socket venues exist: transport and venue are independent axes.

    See docs/adr/018-broker-transport-venue-matrix.md.
    """

    def test_socket_live_without_live_trading_enabled_raises(self):
        account = make_broker_account(broker_type="interactive_brokers_socket", live_trading_enabled=0)
        with (
            patch("infrastructure.brokers.factory.build_ibkr_socket_broker") as mock_build,
            pytest.raises(LiveTradingNotEnabledError, match="live_trading_enabled"),
        ):
            get_broker_for_account(account)
        # The guard runs before anything opens a socket.
        mock_build.assert_not_called()

    def test_socket_live_with_live_trading_enabled_connects(self):
        account = make_broker_account(broker_type="interactive_brokers_socket", live_trading_enabled=1)
        adapter = MagicMock()
        with patch("infrastructure.brokers.factory.build_ibkr_socket_broker", return_value=adapter):
            assert get_broker_for_account(account) is adapter
        # A live socket account is never asked to prove it is a paper account.
        adapter.managed_accounts.assert_not_called()

    def test_socket_paper_connects_without_live_trading_enabled(self):
        account = make_broker_account(broker_type="interactive_brokers_socket_paper", live_trading_enabled=0)
        adapter = MagicMock()
        adapter.managed_accounts.return_value = ["DU1234567"]
        with patch("infrastructure.brokers.factory.build_ibkr_socket_broker", return_value=adapter):
            assert get_broker_for_account(account) is adapter
        adapter.disconnect.assert_not_called()

    def test_socket_paper_refuses_a_live_account_and_disconnects(self):
        account = make_broker_account(broker_type="interactive_brokers_socket_paper", live_trading_enabled=0)
        adapter = MagicMock()
        adapter.managed_accounts.return_value = ["U1234567"]
        with (
            patch("infrastructure.brokers.factory.build_ibkr_socket_broker", return_value=adapter),
            pytest.raises(PaperBrokerAccountMismatchError, match="not an IBKR paper account"),
        ):
            get_broker_for_account(account)
        # The socket is already open by the time the assertion can run, so it
        # has to be closed on the way out.
        adapter.disconnect.assert_called_once_with()

    def test_socket_paper_refuses_when_any_reachable_account_is_live(self):
        """The session can trade every managed account, so one live entry is fatal."""
        account = make_broker_account(broker_type="interactive_brokers_socket_paper", live_trading_enabled=0)
        adapter = MagicMock()
        adapter.managed_accounts.return_value = ["DU1234567", "U7654321"]
        with (
            patch("infrastructure.brokers.factory.build_ibkr_socket_broker", return_value=adapter),
            pytest.raises(PaperBrokerAccountMismatchError),
        ):
            get_broker_for_account(account)
        adapter.disconnect.assert_called_once_with()

    def test_socket_paper_refuses_when_no_account_is_reported(self):
        """An empty list proves nothing; failing closed is the only safe read."""
        account = make_broker_account(broker_type="interactive_brokers_socket_paper", live_trading_enabled=0)
        adapter = MagicMock()
        adapter.managed_accounts.return_value = []
        with (
            patch("infrastructure.brokers.factory.build_ibkr_socket_broker", return_value=adapter),
            pytest.raises(PaperBrokerAccountMismatchError, match="<none reported>"),
        ):
            get_broker_for_account(account)
        adapter.disconnect.assert_called_once_with()

    def test_socket_paper_refuses_even_when_live_trading_enabled(self):
        account = make_broker_account(broker_type="interactive_brokers_socket_paper", live_trading_enabled=1)
        adapter = MagicMock()
        adapter.managed_accounts.return_value = ["U1234567"]
        with (
            patch("infrastructure.brokers.factory.build_ibkr_socket_broker", return_value=adapter),
            pytest.raises(PaperBrokerAccountMismatchError),
        ):
            get_broker_for_account(account)

    def test_socket_paper_prefix_match_is_case_insensitive(self):
        account = make_broker_account(broker_type="interactive_brokers_socket_paper", live_trading_enabled=0)
        adapter = MagicMock()
        adapter.managed_accounts.return_value = ["du1234567"]
        with patch("infrastructure.brokers.factory.build_ibkr_socket_broker", return_value=adapter):
            assert get_broker_for_account(account) is adapter

    def test_socket_paper_disconnects_when_account_lookup_fails(self):
        account = make_broker_account(broker_type="interactive_brokers_socket_paper", live_trading_enabled=0)
        adapter = MagicMock()
        adapter.managed_accounts.side_effect = RuntimeError("not connected")
        with (
            patch("infrastructure.brokers.factory.build_ibkr_socket_broker", return_value=adapter),
            pytest.raises(RuntimeError, match="not connected"),
        ):
            get_broker_for_account(account)
        adapter.disconnect.assert_called_once_with()

    def test_retired_broker_type_is_refused(self):
        """`interactive_brokers` was renamed with no alias, so it must fail loudly.

        Silently simulating it would answer a broker request with fabricated
        fills — worse than an error for an account meant to reach IBKR.
        """
        account = make_broker_account(broker_type="interactive_brokers", live_trading_enabled=1)
        with pytest.raises(UnknownBrokerTypeError, match="interactive_brokers"):
            get_broker_for_account(account)

    def test_unknown_broker_type_is_refused(self):
        account = make_broker_account(broker_type="interactive_brokers_scoket", live_trading_enabled=0)
        with pytest.raises(UnknownBrokerTypeError, match="not a known broker"):
            get_broker_for_account(account)

    def test_unknown_broker_type_error_is_runtime_error(self):
        assert issubclass(UnknownBrokerTypeError, RuntimeError)


class TestLiveTradingSafety:
    def test_paper_adapter_never_requires_live_enabled(self):
        for flag in (0, None):
            broker = get_broker_for_account(make_broker_account(broker_type="paper", live_trading_enabled=flag))
            assert isinstance(broker, PaperBrokerAdapter)

    def test_live_trading_not_enabled_error_is_runtime_error(self):
        assert issubclass(LiveTradingNotEnabledError, RuntimeError)
