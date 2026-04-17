from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
from pathlib import Path

import pytest


def _load():
    return importlib.import_module(
        "trading.interfaces.runtime.jobs.daily_paper_trading"
    )


# ---------------------------------------------------------------------------
# parse_account_trade_caps
# ---------------------------------------------------------------------------

class TestParseAccountTradeCaps:
    def test_empty_string_returns_empty_dict(self) -> None:
        assert _load().parse_account_trade_caps("") == {}

    def test_whitespace_only_returns_empty_dict(self) -> None:
        assert _load().parse_account_trade_caps("   ") == {}

    def test_single_entry(self) -> None:
        result = _load().parse_account_trade_caps("momentum_5k:1-5")
        assert result == {"momentum_5k": (1, 5)}

    def test_multiple_entries(self) -> None:
        result = _load().parse_account_trade_caps("acct_a:2-8,acct_b:1-3")
        assert result == {"acct_a": (2, 8), "acct_b": (1, 3)}

    def test_missing_colon_raises(self) -> None:
        with pytest.raises(ValueError, match="account:min-max"):
            _load().parse_account_trade_caps("acct1-5")

    def test_missing_dash_raises(self) -> None:
        with pytest.raises(ValueError, match="account:min-max"):
            _load().parse_account_trade_caps("acct:15")

    def test_min_trades_below_one_raises(self) -> None:
        with pytest.raises(ValueError, match="min trades must be >= 1"):
            _load().parse_account_trade_caps("acct:0-5")

    def test_max_less_than_min_raises(self) -> None:
        with pytest.raises(ValueError, match="max trades must be >= min trades"):
            _load().parse_account_trade_caps("acct:5-2")


# ---------------------------------------------------------------------------
# load_trade_caps_config
# ---------------------------------------------------------------------------

class TestLoadTradeCapsConfig:
    def test_missing_file_returns_none_and_empty(self, tmp_path: Path) -> None:
        default_caps, account_caps, excluded = _load().load_trade_caps_config(tmp_path / "missing.json")
        assert default_caps is None
        assert account_caps == {}
        assert excluded == []

    def test_valid_config_with_default_and_accounts(self, tmp_path: Path) -> None:
        config = {
            "default": {"min": 1, "max": 5},
            "accounts": {
                "special_acct": {"min": 2, "max": 8},
            },
        }
        path = tmp_path / "caps.json"
        path.write_text(json.dumps(config), encoding="utf-8")

        default_caps, account_caps, excluded = _load().load_trade_caps_config(path)
        assert default_caps == (1, 5)
        assert account_caps == {"special_acct": (2, 8)}
        assert excluded == []

    def test_config_without_default_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "caps.json"
        path.write_text(json.dumps({"accounts": {}}), encoding="utf-8")
        default_caps, _, _excluded = _load().load_trade_caps_config(path)
        assert default_caps is None

    def test_excluded_accounts_are_returned(self, tmp_path: Path) -> None:
        config = {
            "excluded": ["test_account_bt", "sandbox"],
            "default": {"min": 1, "max": 5},
            "accounts": {},
        }
        path = tmp_path / "caps.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        _, _, excluded = _load().load_trade_caps_config(path)
        assert excluded == ["test_account_bt", "sandbox"]

    def test_non_dict_root_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "caps.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with pytest.raises(ValueError, match="JSON object"):
            _load().load_trade_caps_config(path)

    def test_default_missing_min_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "caps.json"
        path.write_text(json.dumps({"default": {"max": 5}}), encoding="utf-8")
        with pytest.raises(ValueError, match="min"):
            _load().load_trade_caps_config(path)

    def test_account_caps_not_dict_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "caps.json"
        path.write_text(json.dumps({"accounts": "bad"}), encoding="utf-8")
        with pytest.raises(ValueError, match="object"):
            _load().load_trade_caps_config(path)


# ---------------------------------------------------------------------------
# resolve_trade_caps
# ---------------------------------------------------------------------------

class TestResolveTradeCaps:
    def _resolve(self, accounts, **kwargs):
        defaults = {
            "configured_default_caps": None,
            "configured_account_caps": {},
            "primary_accounts": set(),
            "primary_min_trades": 1,
            "primary_max_trades": 5,
            "other_min_trades": 1,
            "other_max_trades": 11,
            "account_trade_cap_overrides": {},
        }
        defaults.update(kwargs)
        return _load().resolve_trade_caps(accounts, **defaults)

    def test_cli_override_takes_highest_priority(self) -> None:
        result = self._resolve(
            ["acct"],
            configured_account_caps={"acct": (2, 8)},
            account_trade_cap_overrides={"acct": (3, 3)},
        )
        assert result["acct"] == (3, 3)

    def test_configured_account_cap_used_when_no_override(self) -> None:
        result = self._resolve(["acct"], configured_account_caps={"acct": (2, 7)})
        assert result["acct"] == (2, 7)

    def test_configured_default_used_when_no_account_entry(self) -> None:
        result = self._resolve(["acct"], configured_default_caps=(1, 6))
        assert result["acct"] == (1, 6)

    def test_primary_account_uses_primary_limits(self) -> None:
        result = self._resolve(
            ["primary_acct"],
            primary_accounts={"primary_acct"},
            primary_min_trades=2,
            primary_max_trades=4,
        )
        assert result["primary_acct"] == (2, 4)

    def test_non_primary_uses_other_limits(self) -> None:
        result = self._resolve(
            ["other_acct"],
            other_min_trades=1,
            other_max_trades=9,
        )
        assert result["other_acct"] == (1, 9)


# ---------------------------------------------------------------------------
# already_completed_today
# ---------------------------------------------------------------------------

class TestAlreadyCompletedToday:
    def test_returns_false_when_no_logs(self, tmp_path: Path) -> None:
        module = _load()
        assert module.already_completed_today(tmp_path, today=dt.date(2026, 3, 30)) is False

    def test_returns_true_when_sentinel_found(self, tmp_path: Path) -> None:
        module = _load()
        today = dt.date(2026, 3, 30)
        log = tmp_path / f"daily_paper_trading_{today.strftime('%Y%m%d')}_120000.log"
        log.write_text(f"run\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")
        assert module.already_completed_today(tmp_path, today=today) is True

    def test_returns_false_when_sentinel_absent(self, tmp_path: Path) -> None:
        module = _load()
        today = dt.date(2026, 3, 30)
        log = tmp_path / f"daily_paper_trading_{today.strftime('%Y%m%d')}_120000.log"
        log.write_text("partial run\n", encoding="utf-8")
        assert module.already_completed_today(tmp_path, today=today) is False

    def test_uses_todays_date_tag_by_default(self, tmp_path: Path) -> None:
        module = _load()
        today = dt.date.today()
        log = tmp_path / f"daily_paper_trading_{today.strftime('%Y%m%d')}_000000.log"
        log.write_text(f"{module.COMPLETE_SENTINEL}\n", encoding="utf-8")
        assert module.already_completed_today(tmp_path) is True


# ---------------------------------------------------------------------------
# group_accounts_by_caps
# ---------------------------------------------------------------------------

class TestGroupAccountsByCaps:
    def test_single_group(self) -> None:
        module = _load()
        caps = {"a": (1, 5), "b": (1, 5)}
        result = module.group_accounts_by_caps(["a", "b"], caps)
        assert result == {(1, 5): ["a", "b"]}

    def test_multiple_groups(self) -> None:
        module = _load()
        caps = {"a": (1, 5), "b": (1, 11), "c": (1, 5)}
        result = module.group_accounts_by_caps(["a", "b", "c"], caps)
        assert result[(1, 5)] == ["a", "c"]
        assert result[(1, 11)] == ["b"]

    def test_preserves_insertion_order_within_group(self) -> None:
        module = _load()
        caps = {"z": (1, 5), "a": (1, 5), "m": (1, 5)}
        result = module.group_accounts_by_caps(["z", "a", "m"], caps)
        assert result[(1, 5)] == ["z", "a", "m"]

    def test_empty_accounts_returns_empty(self) -> None:
        assert _load().group_accounts_by_caps([], {}) == {}


# ---------------------------------------------------------------------------
# main() — integration flow
# ---------------------------------------------------------------------------

def _run_main(monkeypatch, tmp_path: Path, argv: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["daily_paper_trading"] + argv + ["--repo-root", str(tmp_path)])
    (tmp_path / "local" / "logs").mkdir(parents=True, exist_ok=True)
    return _load().main()


class TestMainFlow:
    def test_duplicate_run_guard_skips_when_already_done(
        self, monkeypatch, tmp_path: Path, capsys
    ) -> None:
        module = _load()
        log_dir = tmp_path / "local" / "logs"
        log_dir.mkdir(parents=True)
        today = dt.date.today().strftime("%Y%m%d")
        (log_dir / f"daily_paper_trading_{today}_000000.log").write_text(
            f"{module.COMPLETE_SENTINEL}\n", encoding="utf-8"
        )
        monkeypatch.setattr(sys, "argv", ["daily_paper_trading", "--repo-root", str(tmp_path)])
        code = module.main()
        assert code == 0
        assert "skipping duplicate run" in capsys.readouterr().out

    def test_force_run_bypasses_duplicate_guard(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        module = _load()
        log_dir = tmp_path / "local" / "logs"
        log_dir.mkdir(parents=True)
        today = dt.date.today().strftime("%Y%m%d")
        (log_dir / f"daily_paper_trading_{today}_000000.log").write_text(
            f"{module.COMPLETE_SENTINEL}\n", encoding="utf-8"
        )

        stream_calls: list[str] = []

        def fake_stream(log_path, label, args, cwd):
            stream_calls.append(label)

        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.stream_command",
            fake_stream,
        )
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.load_all_account_names",
            lambda: ["acct_a"],
        )
        monkeypatch.setattr(sys, "argv", [
            "daily_paper_trading",
            "--repo-root", str(tmp_path),
            "--force-run",
            "--accounts", "acct_a",
        ])
        code = module.main()
        assert code == 0
        assert stream_calls  # stream_command was called
        artifacts = list((tmp_path / "local" / "exports" / "daily_paper_trading").glob("daily_paper_trading_*.json"))
        assert len(artifacts) == 1
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        assert payload["status"] == "success"
        assert payload["completed_steps"]

    def test_unknown_account_returns_1(
        self, monkeypatch, tmp_path: Path, capsys
    ) -> None:
        module = _load()
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.load_all_account_names",
            lambda: ["real_acct"],
        )
        monkeypatch.setattr(sys, "argv", [
            "daily_paper_trading",
            "--repo-root", str(tmp_path),
            "--accounts", "ghost_acct",
        ])
        code = module.main()
        assert code == 1
        assert "Unknown account" in capsys.readouterr().err

    def test_no_accounts_returns_1(
        self, monkeypatch, tmp_path: Path, capsys
    ) -> None:
        module = _load()
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.load_all_account_names",
            lambda: [],
        )
        monkeypatch.setattr(sys, "argv", [
            "daily_paper_trading",
            "--repo-root", str(tmp_path),
            "--accounts", "all",
        ])
        code = module.main()
        assert code == 1
        assert "No accounts" in capsys.readouterr().err

    def test_invalid_primary_trade_cap_returns_1(
        self, monkeypatch, tmp_path: Path, capsys
    ) -> None:
        module = _load()
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.load_all_account_names",
            lambda: ["acct_a"],
        )
        monkeypatch.setattr(sys, "argv", [
            "daily_paper_trading",
            "--repo-root", str(tmp_path),
            "--accounts", "acct_a",
            "--primary-min-trades", "5",
            "--primary-max-trades", "2",
        ])
        code = module.main()
        assert code == 1
        assert "primary-max-trades" in capsys.readouterr().err

    def test_stream_command_exception_returns_1(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        module = _load()
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.load_all_account_names",
            lambda: ["acct_a"],
        )
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.stream_command",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("step failed")),
        )
        monkeypatch.setattr(sys, "argv", [
            "daily_paper_trading",
            "--repo-root", str(tmp_path),
            "--accounts", "acct_a",
        ])
        code = module.main()
        assert code == 1

    def test_success_notification_requires_flag(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        module = _load()
        sent: list[dict[str, object]] = []
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.load_all_account_names",
            lambda: ["acct_a"],
        )
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.stream_command",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.notify_webhook_best_effort",
            lambda **kwargs: sent.append(kwargs) or True,
        )

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "daily_paper_trading",
                "--repo-root",
                str(tmp_path),
                "--accounts",
                "acct_a",
                "--notify-webhook-url",
                "https://example.test/webhook",
            ],
        )
        code = module.main()

        assert code == 0
        assert sent == []

    def test_success_notification_sent_when_enabled(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        module = _load()
        sent: list[dict[str, object]] = []
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.load_all_account_names",
            lambda: ["acct_a"],
        )
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.stream_command",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.notify_webhook_best_effort",
            lambda **kwargs: sent.append(kwargs) or True,
        )

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "daily_paper_trading",
                "--repo-root",
                str(tmp_path),
                "--accounts",
                "acct_a",
                "--notify-webhook-url",
                "https://example.test/webhook",
                "--notify-on-success",
            ],
        )
        code = module.main()

        assert code == 0
        assert len(sent) == 1
        assert sent[0]["status"] == "ok"
        assert sent[0]["event"] == "daily-paper-trading"

    def test_failure_notification_sent_when_run_fails(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        module = _load()
        sent: list[dict[str, object]] = []
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.load_all_account_names",
            lambda: ["acct_a"],
        )
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.stream_command",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("step failed")),
        )
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.daily_paper_trading.notify_webhook_best_effort",
            lambda **kwargs: sent.append(kwargs) or True,
        )

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "daily_paper_trading",
                "--repo-root",
                str(tmp_path),
                "--accounts",
                "acct_a",
                "--notify-webhook-url",
                "https://example.test/webhook",
            ],
        )
        code = module.main()

        assert code == 1
        assert len(sent) == 1
        assert sent[0]["status"] == "fail"
        artifacts = list((tmp_path / "local" / "exports" / "daily_paper_trading").glob("daily_paper_trading_*.json"))
        assert len(artifacts) == 1
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        assert payload["status"] == "failed"
        assert payload["error"] == "step failed"
