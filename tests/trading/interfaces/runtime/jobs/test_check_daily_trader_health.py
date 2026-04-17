from __future__ import annotations

import importlib
import json
import os
import sys
import time
from pathlib import Path


def _load():
    return importlib.import_module(
        "trading.interfaces.runtime.jobs.check_daily_trader_health"
    )


def _run_main(monkeypatch, argv: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["check_daily_trader_health"] + argv)
    return _load().main()


# ---------------------------------------------------------------------------
# _make_payload / _emit helpers
# ---------------------------------------------------------------------------

class TestEmit:
    def test_human_readable_output(self, capsys) -> None:
        module = _load()
        payload = module._make_payload(
            status="ok",
            message="All good",
            latest_log="/tmp/foo.log",
            latest_log_age_hours=2.5,
            sentinel_found=True,
        )
        module._emit(payload, as_json=False)
        out = capsys.readouterr().out
        assert "[OK] All good" in out
        assert "latest_log=/tmp/foo.log" in out
        assert "latest_log_age_hours=2.50" in out

    def test_json_output(self, capsys) -> None:
        module = _load()
        payload = module._make_payload(
            status="fail",
            message="Stale",
            latest_log=None,
            latest_log_age_hours=None,
            sentinel_found=False,
        )
        module._emit(payload, as_json=True)
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "fail"
        assert data["sentinel_found"] is False


# ---------------------------------------------------------------------------
# main() — argument validation
# ---------------------------------------------------------------------------

class TestMainArgValidation:
    def test_max_age_hours_zero_returns_2(self, monkeypatch) -> None:
        code = _run_main(monkeypatch, ["--max-age-hours", "0", "--repo-root", "."])
        assert code == 2

    def test_max_age_hours_negative_returns_2(self, monkeypatch) -> None:
        code = _run_main(monkeypatch, ["--max-age-hours", "-1", "--repo-root", "."])
        assert code == 2


# ---------------------------------------------------------------------------
# main() — log-directory scenarios
# ---------------------------------------------------------------------------

class TestMainLogScenarios:
    def _log_dir(self, tmp_path: Path) -> Path:
        log_dir = tmp_path / "local" / "logs"
        log_dir.mkdir(parents=True)
        return log_dir

    def test_no_logs_returns_1(self, monkeypatch, tmp_path: Path, capsys) -> None:
        self._log_dir(tmp_path)
        code = _run_main(monkeypatch, ["--repo-root", str(tmp_path)])
        assert code == 1
        assert "No daily trader logs found" in capsys.readouterr().out

    def test_stale_log_returns_1(self, monkeypatch, tmp_path: Path, capsys) -> None:
        log_dir = self._log_dir(tmp_path)
        log = log_dir / "daily_paper_trading_20260417_120000.log"
        log.write_text("anything\n", encoding="utf-8")
        # set mtime to 48 hours ago
        old_time = time.time() - 48 * 3600
        os.utime(log, (old_time, old_time))

        code = _run_main(monkeypatch, ["--repo-root", str(tmp_path), "--max-age-hours", "24"])
        assert code == 1
        assert "stale" in capsys.readouterr().out

    def test_recent_log_missing_sentinel_returns_1(
        self, monkeypatch, tmp_path: Path, capsys
    ) -> None:
        log_dir = self._log_dir(tmp_path)
        (log_dir / "daily_paper_trading_20260417_120000.log").write_text(
            "partial run\n", encoding="utf-8"
        )
        code = _run_main(monkeypatch, ["--repo-root", str(tmp_path), "--max-age-hours", "9999"])
        assert code == 1
        assert "sentinel" in capsys.readouterr().out

    def test_recent_log_with_sentinel_returns_0(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        module = _load()
        log_dir = self._log_dir(tmp_path)
        (log_dir / "daily_paper_trading_20260417_120000.log").write_text(
            f"run started\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8"
        )
        code = _run_main(monkeypatch, ["--repo-root", str(tmp_path), "--max-age-hours", "9999"])
        assert code == 0

    def test_startup_log_is_ignored_when_execution_log_exists(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        module = _load()
        log_dir = self._log_dir(tmp_path)
        (log_dir / "daily_paper_trading_20260417_120000.log").write_text(
            f"run started\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8"
        )
        startup_log = log_dir / "daily_paper_trading_startup_20260417.log"
        startup_log.write_text("later startup without sentinel\n", encoding="utf-8")
        now = time.time()
        os.utime(startup_log, (now, now))

        code = _run_main(monkeypatch, ["--repo-root", str(tmp_path), "--max-age-hours", "9999"])
        assert code == 0

    def test_json_flag_emits_json(
        self, monkeypatch, tmp_path: Path, capsys
    ) -> None:
        module = _load()
        log_dir = self._log_dir(tmp_path)
        (log_dir / "daily_paper_trading_20260417_120000.log").write_text(
            f"{module.COMPLETE_SENTINEL}\n", encoding="utf-8"
        )
        code = _run_main(
            monkeypatch,
            ["--repo-root", str(tmp_path), "--max-age-hours", "9999", "--json"],
        )
        assert code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "ok"
        assert data["sentinel_found"] is True

    def test_failure_sends_notification_when_webhook_configured(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        log_dir = self._log_dir(tmp_path)
        (log_dir / "daily_paper_trading_20260417_120000.log").write_text(
            "partial run\n", encoding="utf-8"
        )

        sent: list[dict[str, object]] = []
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.check_daily_trader_health.notify_webhook_best_effort",
            lambda **kwargs: sent.append(kwargs) or True,
        )

        code = _run_main(
            monkeypatch,
            [
                "--repo-root",
                str(tmp_path),
                "--max-age-hours",
                "9999",
                "--notify-webhook-url",
                "https://example.test/webhook",
            ],
        )

        assert code == 1
        assert len(sent) == 1
        assert sent[0]["status"] == "fail"
        assert sent[0]["event"] == "daily-trader-health"

    def test_success_does_not_send_notification_without_notify_on_ok(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        module = _load()
        log_dir = self._log_dir(tmp_path)
        (log_dir / "daily_paper_trading_20260417_120000.log").write_text(
            f"{module.COMPLETE_SENTINEL}\n", encoding="utf-8"
        )

        sent: list[dict[str, object]] = []
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.check_daily_trader_health.notify_webhook_best_effort",
            lambda **kwargs: sent.append(kwargs) or True,
        )

        code = _run_main(
            monkeypatch,
            [
                "--repo-root",
                str(tmp_path),
                "--max-age-hours",
                "9999",
                "--notify-webhook-url",
                "https://example.test/webhook",
            ],
        )

        assert code == 0
        assert sent == []

    def test_success_sends_notification_with_notify_on_ok(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        module = _load()
        log_dir = self._log_dir(tmp_path)
        (log_dir / "daily_paper_trading_20260417_120000.log").write_text(
            f"{module.COMPLETE_SENTINEL}\n", encoding="utf-8"
        )

        sent: list[dict[str, object]] = []
        monkeypatch.setattr(
            "trading.interfaces.runtime.jobs.check_daily_trader_health.notify_webhook_best_effort",
            lambda **kwargs: sent.append(kwargs) or True,
        )

        code = _run_main(
            monkeypatch,
            [
                "--repo-root",
                str(tmp_path),
                "--max-age-hours",
                "9999",
                "--notify-webhook-url",
                "https://example.test/webhook",
                "--notify-on-ok",
            ],
        )

        assert code == 0
        assert len(sent) == 1
        assert sent[0]["status"] == "ok"
