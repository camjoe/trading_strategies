from types import SimpleNamespace
import sys

import pytest

from common.time import utc_now_iso
from trading.domain.exceptions import RuntimeTradeThrottleExceededError
from trading.interfaces.runtime.jobs import daily_auto_trader as auto_trader
from trading.repositories.global_settings_repository import upsert_runtime_throttle_settings
import trading.services.auto_trader_runtime_service as runtime_service
import trading.services.trade_execution_service as trade_execution_service


def _base_account(**overrides):
    base = {
        "option_strike_offset_pct": 5.0,
        "target_delta_min": None,
        "target_delta_max": None,
        "iv_rank_min": None,
        "iv_rank_max": None,
        "max_contracts_per_trade": None,
        "max_premium_per_trade": None,
        "option_min_dte": 120,
        "option_max_dte": 365,
        "option_type": "call",
        "learning_enabled": 0,
        "risk_policy": "none",
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "instrument_mode": "equity",
        "initial_cash": 5000.0,
        "id": 1,
        "strategy": "trend",
        "rotation_enabled": 0,
        "rotation_interval_days": None,
        "rotation_schedule": None,
        "rotation_active_index": 0,
        "rotation_last_at": None,
        "rotation_active_strategy": None,
        "rotation_mode": "time",
        "rotation_optimality_mode": "previous_period_best",
        "rotation_lookback_days": 180,
    }
    base.update(overrides)
    return base


class TestInputLoadingAndPrimitiveHelpers:
    def test_parse_args_reads_cli_values(self, monkeypatch):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "auto_trader.py",
                "--accounts",
                "acct1,acct2",
                "--tickers-file",
                str(auto_trader.DEFAULT_TICKERS_FILE),
                "--min-trades",
                "2",
                "--max-trades",
                "7",
                "--fee",
                "1.25",
                "--seed",
                "99",
            ],
        )

        args = auto_trader.parse_args()
        assert args.accounts == "acct1,acct2"
        assert args.tickers_file == auto_trader.DEFAULT_TICKERS_FILE
        assert args.min_trades == 2
        assert args.max_trades == 7
        assert args.fee == pytest.approx(1.25)
        assert args.seed == 99

class TestCliMainFlow:
    def test_main_validation_errors(self, monkeypatch):
        args = SimpleNamespace(
            min_trades=0,
            max_trades=1,
            seed=None,
            accounts="acct1",
            tickers_file="trading/config/trade_universe.txt",
            fee=0.0,
        )
        monkeypatch.setattr(auto_trader, "parse_args", lambda: args)
        with pytest.raises(ValueError, match="min-trades"):
            auto_trader.main()

    def test_main_happy_path_dispatches_accounts(self, monkeypatch, capsys):
        class _Conn:
            closed = False

            def close(self):
                self.closed = True

        conn = _Conn()
        args = SimpleNamespace(
            min_trades=1,
            max_trades=2,
            seed=123,
            accounts="acct1,acct2",
            tickers_file="trading/config/trade_universe.txt",
            fee=1.0,
        )

        calls = []

        monkeypatch.setattr(auto_trader, "parse_args", lambda: args)
        monkeypatch.setattr(auto_trader, "load_tickers_from_file", lambda _p: ["AAPL", "MSFT"])
        monkeypatch.setattr(auto_trader, "fetch_latest_prices", lambda _u: {"AAPL": 100.0, "MSFT": 200.0})
        monkeypatch.setattr(auto_trader, "build_iv_rank_proxy", lambda _u: {"AAPL": 40.0})
        monkeypatch.setattr(auto_trader, "ensure_db", lambda: conn)

        def _fake_run_for_account(**kwargs):
            calls.append(kwargs["account_name"])
            return 2

        monkeypatch.setattr(auto_trader, "run_for_account", _fake_run_for_account)

        auto_trader.main()

        assert calls == ["acct1", "acct2"]
        out = capsys.readouterr().out
        assert "acct1: executed 2 trades" in out
        assert "acct2: executed 2 trades" in out
        assert conn.closed is True

    def test_main_additional_validation_paths(self, monkeypatch):
        args = SimpleNamespace(
            min_trades=2,
            max_trades=1,
            seed=None,
            accounts="acct1",
            tickers_file="trading/config/trade_universe.txt",
            fee=0.0,
        )
        monkeypatch.setattr(auto_trader, "parse_args", lambda: args)
        with pytest.raises(ValueError, match="max-trades"):
            auto_trader.main()

        args.max_trades = 2
        args.accounts = "  ,   "
        with pytest.raises(ValueError, match="No accounts"):
            auto_trader.main()

    def test_main_empty_universe_and_no_prices(self, monkeypatch):
        args = SimpleNamespace(
            min_trades=1,
            max_trades=1,
            seed=None,
            accounts="acct1",
            tickers_file="trading/config/trade_universe.txt",
            fee=0.0,
        )
        monkeypatch.setattr(auto_trader, "parse_args", lambda: args)

        monkeypatch.setattr(auto_trader, "load_tickers_from_file", lambda _p: [])
        with pytest.raises(ValueError, match="Ticker universe is empty"):
            auto_trader.main()

        monkeypatch.setattr(auto_trader, "load_tickers_from_file", lambda _p: ["AAPL"])
        monkeypatch.setattr(auto_trader, "fetch_latest_prices", lambda _u: {})
        with pytest.raises(ValueError, match="Could not fetch any prices"):
            auto_trader.main()

    def test_main_closes_connection_when_run_for_account_fails(self, monkeypatch):
        class _Conn:
            closed = False

            def close(self):
                self.closed = True

        conn = _Conn()
        args = SimpleNamespace(
            min_trades=1,
            max_trades=1,
            seed=None,
            accounts="acct1",
            tickers_file="trading/config/trade_universe.txt",
            fee=0.0,
        )

        monkeypatch.setattr(auto_trader, "parse_args", lambda: args)
        monkeypatch.setattr(auto_trader, "load_tickers_from_file", lambda _p: ["AAPL"])
        monkeypatch.setattr(auto_trader, "fetch_latest_prices", lambda _u: {"AAPL": 100.0})
        monkeypatch.setattr(auto_trader, "build_iv_rank_proxy", lambda _u: {})
        monkeypatch.setattr(auto_trader, "ensure_db", lambda: conn)
        monkeypatch.setattr(auto_trader, "run_for_account", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

        with pytest.raises(RuntimeError, match="boom"):
            auto_trader.main()

        assert conn.closed is True
# ---------------------------------------------------------------------------
# Trade Loop Orchestration
# ---------------------------------------------------------------------------

class TestTradeLoopOrchestration:
    def test_run_for_account_executes_buy_and_records_trade(self, monkeypatch):
        account = _base_account(learning_enabled=1, id=42)
        state = SimpleNamespace(cash=1000.0, positions={}, avg_cost={})

        monkeypatch.setattr(runtime_service, "get_account", lambda _conn, _name: account)
        monkeypatch.setattr(runtime_service, "load_trades", lambda _conn, _id: [])
        monkeypatch.setattr(runtime_service, "compute_account_state", lambda *_args, **_kwargs: state)
        monkeypatch.setattr(trade_execution_service.random, "randint", lambda a, b: 1)  # target trades = 1
        monkeypatch.setattr(runtime_service.auto_trader_policy, "choose_side", lambda *_args, **_kwargs: "buy")
        monkeypatch.setattr(runtime_service, "prepare_buy_trade_impl", lambda *_args, **_kwargs: ("AAPL", 2, 101.0, None, None))
        monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: "2026-03-14T00:00:00Z")

        calls = []
        monkeypatch.setattr(runtime_service, "insert_broker_order", lambda *_a, **_k: None)
        monkeypatch.setattr(runtime_service, "insert_order_fill", lambda *_a, **_k: None)
        monkeypatch.setattr(runtime_service, "record_trade", lambda conn, **kwargs: calls.append(kwargs))

        executed = auto_trader.run_for_account(
            conn=object(),
            account_name="acct",
            universe=["AAPL"],
            prices={"AAPL": 101.0},
            iv_rank_proxy={},
            min_trades=1,
            max_trades=1,
            fee=0.0,
        )
        assert executed == 1
        assert calls[0]["side"] == "buy"
        assert calls[0]["ticker"] == "AAPL"
        assert "selection=heuristic-exploration" in calls[0]["note"]
        assert "strategy=trend" in calls[0]["note"]


    def test_run_for_account_forced_sell_note_includes_risk(self, monkeypatch):
        account = _base_account(learning_enabled=0, id=7, risk_policy="fixed_stop", stop_loss_pct=5.0)
        state = SimpleNamespace(cash=1000.0, positions={"AAPL": 3.0}, avg_cost={"AAPL": 100.0})

        monkeypatch.setattr(runtime_service, "get_account", lambda _conn, _name: account)
        monkeypatch.setattr(runtime_service, "load_trades", lambda _conn, _id: [])
        monkeypatch.setattr(runtime_service, "compute_account_state", lambda *_args, **_kwargs: state)
        monkeypatch.setattr(trade_execution_service.random, "randint", lambda a, b: 1)
        monkeypatch.setattr(runtime_service.auto_trader_policy, "choose_sell_ticker_by_risk", lambda *_args, **_kwargs: "AAPL")
        monkeypatch.setattr(runtime_service, "prepare_sell_trade_impl", lambda *_args, **_kwargs: ("AAPL", 1, 95.0))
        monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: "2026-03-14T00:00:00Z")

        calls = []
        monkeypatch.setattr(runtime_service, "insert_broker_order", lambda *_a, **_k: None)
        monkeypatch.setattr(runtime_service, "insert_order_fill", lambda *_a, **_k: None)
        monkeypatch.setattr(runtime_service, "record_trade", lambda conn, **kwargs: calls.append(kwargs))

        executed = auto_trader.run_for_account(
            conn=object(),
            account_name="acct",
            universe=["AAPL"],
            prices={"AAPL": 95.0},
            iv_rank_proxy={},
            min_trades=1,
            max_trades=1,
            fee=0.0,
        )
        assert executed == 1
        assert calls[0]["side"] == "sell"
        assert "risk=fixed_stop" in calls[0]["note"]


    def test_run_for_account_skips_iteration_when_trade_not_preparable(self, monkeypatch):
        account = _base_account(learning_enabled=1, id=11)
        state = SimpleNamespace(cash=1000.0, positions={}, avg_cost={})

        monkeypatch.setattr(runtime_service, "get_account", lambda _conn, _name: account)
        monkeypatch.setattr(runtime_service, "load_trades", lambda _conn, _id: [])
        monkeypatch.setattr(runtime_service, "compute_account_state", lambda *_args, **_kwargs: state)
        monkeypatch.setattr(trade_execution_service.random, "randint", lambda a, b: 1)
        monkeypatch.setattr(runtime_service, "prepare_trade_selection_impl", lambda *_args, **_kwargs: None)

        calls = []
        monkeypatch.setattr(runtime_service, "record_trade", lambda conn, **kwargs: calls.append(kwargs))

        executed = auto_trader.run_for_account(
            conn=object(),
            account_name="acct",
            universe=["AAPL"],
            prices={"AAPL": 101.0},
            iv_rank_proxy={},
            min_trades=1,
            max_trades=1,
            fee=0.0,
        )

        assert executed == 0
        assert calls == []

    def test_run_for_account_stops_cleanly_when_global_runtime_day_cap_is_hit(self, monkeypatch, conn):
        account = _base_account(learning_enabled=1, id=11)
        state = SimpleNamespace(cash=1000.0, positions={}, avg_cost={})
        upsert_runtime_throttle_settings(
            conn,
            runtime_max_trades_per_day=1,
            runtime_max_trades_per_minute=None,
            updated_at=utc_now_iso(),
        )
        conn.execute(
            """
            INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (11, "AAPL", "buy", 1.0, 100.0, 0.0, "2026-03-14T00:00:00Z", "existing"),
        )
        conn.commit()

        monkeypatch.setattr(runtime_service, "get_account", lambda _conn, _name: account)
        monkeypatch.setattr(runtime_service, "load_trades", lambda _conn, _id: [])
        monkeypatch.setattr(runtime_service, "compute_account_state", lambda *_args, **_kwargs: state)
        monkeypatch.setattr(trade_execution_service.random, "randint", lambda a, b: 2)
        monkeypatch.setattr(runtime_service.auto_trader_policy, "choose_side", lambda *_args, **_kwargs: "buy")
        monkeypatch.setattr(
            runtime_service,
            "prepare_buy_trade_impl",
            lambda *_args, **_kwargs: ("AAPL", 1, 101.0, None, None),
        )
        monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: "2026-03-14T00:00:30Z")

        calls = []
        monkeypatch.setattr(runtime_service, "insert_broker_order", lambda *_a, **_k: None)
        monkeypatch.setattr(runtime_service, "insert_order_fill", lambda *_a, **_k: None)
        monkeypatch.setattr(runtime_service, "record_trade", lambda conn, **kwargs: calls.append(kwargs))

        executed = auto_trader.run_for_account(
            conn=conn,
            account_name="acct",
            universe=["AAPL"],
            prices={"AAPL": 101.0},
            iv_rank_proxy={},
            min_trades=2,
            max_trades=2,
            fee=0.0,
        )

        assert executed == 0
        assert calls == []

    def test_run_for_account_breaks_only_on_runtime_throttle_exception(self, monkeypatch):
        account = _base_account(learning_enabled=1, id=42)
        state = SimpleNamespace(cash=1000.0, positions={}, avg_cost={})

        monkeypatch.setattr(runtime_service, "get_account", lambda _conn, _name: account)
        monkeypatch.setattr(runtime_service, "load_trades", lambda _conn, _id: [])
        monkeypatch.setattr(runtime_service, "compute_account_state", lambda *_args, **_kwargs: state)
        monkeypatch.setattr(trade_execution_service.random, "randint", lambda a, b: 1)
        monkeypatch.setattr(runtime_service.auto_trader_policy, "choose_side", lambda *_args, **_kwargs: "buy")
        monkeypatch.setattr(
            runtime_service,
            "prepare_buy_trade_impl",
            lambda *_args, **_kwargs: ("AAPL", 2, 101.0, None, None),
        )
        monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: "2026-03-14T00:00:00Z")

        monkeypatch.setattr(
            runtime_service,
            "enforce_runtime_trade_throttles",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeTradeThrottleExceededError("cap hit")),
        )

        executed = auto_trader.run_for_account(
            conn=object(),
            account_name="acct",
            universe=["AAPL"],
            prices={"AAPL": 101.0},
            iv_rank_proxy={},
            min_trades=1,
            max_trades=1,
            fee=0.0,
        )

        assert executed == 0


class TestRotationAwareTradeLoop:
    def test_run_for_account_uses_rotated_active_strategy(self, monkeypatch):
        initial_account = _base_account(
            id=11,
            strategy="trend",
            rotation_enabled=1,
            rotation_interval_days=7,
            rotation_schedule='["trend","mean_reversion"]',
            rotation_active_index=0,
            rotation_last_at="2026-03-01T00:00:00Z",
            rotation_active_strategy="trend",
        )
        rotated_account = _base_account(
            id=11,
            strategy="mean_reversion",
            rotation_enabled=1,
            rotation_interval_days=7,
            rotation_schedule='["trend","mean_reversion"]',
            rotation_active_index=1,
            rotation_last_at="2026-03-17T00:00:00Z",
            rotation_active_strategy="mean_reversion",
        )
        state = SimpleNamespace(cash=1000.0, positions={}, avg_cost={})

        monkeypatch.setattr(runtime_service, "get_account", lambda _conn, _name: initial_account)
        monkeypatch.setattr(runtime_service, "rotate_runtime_account_if_due_impl", lambda _conn, _name, _acct, _now, _deps: rotated_account)
        monkeypatch.setattr(runtime_service, "load_trades", lambda _conn, _id: [])
        monkeypatch.setattr(runtime_service, "compute_account_state", lambda *_args, **_kwargs: state)
        monkeypatch.setattr(trade_execution_service.random, "randint", lambda a, b: 1)
        monkeypatch.setattr(
            runtime_service.auto_trader_policy,
            "choose_side",
            lambda _forced, _sell, strategy_name=None: "buy" if strategy_name == "mean_reversion" else "sell",
        )
        monkeypatch.setattr(runtime_service, "prepare_buy_trade_impl", lambda *_args, **_kwargs: ("AAPL", 1, 100.0, None, None))
        monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: "2026-03-17T00:00:00Z")

        calls = []
        monkeypatch.setattr(runtime_service, "insert_broker_order", lambda *_a, **_k: None)
        monkeypatch.setattr(runtime_service, "insert_order_fill", lambda *_a, **_k: None)
        monkeypatch.setattr(runtime_service, "record_trade", lambda _conn, **kwargs: calls.append(kwargs))

        executed = auto_trader.run_for_account(
            conn=object(),
            account_name="acct",
            universe=["AAPL"],
            prices={"AAPL": 100.0},
            iv_rank_proxy={},
            min_trades=1,
            max_trades=1,
            fee=0.0,
        )
        assert executed == 1
        assert calls[0]["side"] == "buy"
        assert "strategy=mean_reversion" in calls[0]["note"]
