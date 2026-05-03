from __future__ import annotations

from types import SimpleNamespace


class FakeParser:
    def __init__(self, args):
        self._args = args

    def parse_args(self):
        return self._args

    def error(self, message: str):
        raise RuntimeError(message)


class FakeConn:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def configure_account_args(**overrides):
    base = {
        "command": "configure-account",
        "account": "acct1",
        "display_name": None,
        "goal_min_return_pct": None,
        "goal_max_return_pct": None,
        "goal_period": None,
        "learning_enabled": False,
        "learning_disabled": False,
        "risk_policy": None,
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "trade_size_pct": None,
        "max_position_pct": None,
        "instrument_mode": None,
        "option_strike_offset_pct": None,
        "option_min_dte": None,
        "option_max_dte": None,
        "option_type": None,
        "target_delta_min": None,
        "target_delta_max": None,
        "max_premium_per_trade": None,
        "max_contracts_per_trade": None,
        "iv_rank_min": None,
        "iv_rank_max": None,
        "roll_dte_threshold": None,
        "profit_take_pct": None,
        "max_loss_pct": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def install_main_harness(monkeypatch, cli_main_module, args, conn: FakeConn | None = None) -> FakeConn:
    fake_conn = conn or FakeConn()
    monkeypatch.setattr(cli_main_module, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr(cli_main_module, "ensure_db", lambda: fake_conn)
    return fake_conn


__all__ = [
    "FakeConn",
    "FakeParser",
    "configure_account_args",
    "install_main_harness",
]
