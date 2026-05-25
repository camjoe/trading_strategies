"""Tests for trading.interfaces.runtime.jobs.maintenance.burn_in_status."""

from __future__ import annotations

import datetime as _real_dt
import importlib
import json
import sys
from pathlib import Path

MODULE = "trading.interfaces.runtime.jobs.maintenance.burn_in_status"
DEFAULT_FAKE_NOW = _real_dt.datetime(2026, 5, 20, 14, 0, 0)


def _mod():
    return importlib.import_module(MODULE)


def _write_artifact(export_dir: Path, date_str: str, time_str: str, status: str, **extra) -> Path:
    """Write a fake daily_paper_trading artifact JSON to *export_dir*."""
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = f"daily_paper_trading_{date_str}_{time_str}.json"
    payload: dict = {"status": status, "started_at": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}T00:00:00"}
    payload.update(extra)
    path = export_dir / filename
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _patch_now(monkeypatch, fake_now: _real_dt.datetime) -> None:
    """Patch dt.datetime.now() in the module to return *fake_now*."""
    mod = _mod()

    class _FakeDatetime(_real_dt.datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return fake_now

    monkeypatch.setattr(mod.dt, "datetime", _FakeDatetime)


def _run_main(monkeypatch, tmp_path: Path, extra_args: list[str] | None = None) -> int:
    """Run check_burn_in_status.main() with --repo-root pointing at tmp_path."""
    argv = [MODULE, "--repo-root", str(tmp_path)] + (extra_args or [])
    monkeypatch.setattr(sys, "argv", argv)
    mod = _mod()
    return mod.main()


def _run_main_at_now(
    monkeypatch,
    tmp_path: Path,
    *,
    fake_now: _real_dt.datetime = DEFAULT_FAKE_NOW,
    extra_args: list[str] | None = None,
) -> int:
    _patch_now(monkeypatch, fake_now)
    return _run_main(monkeypatch, tmp_path, extra_args)


def _burn_in_artifacts(tmp_path: Path) -> list[Path]:
    return list((tmp_path / "local" / "artifacts").glob("check_burn_in_status_*.json"))


def _load_single_burn_in_artifact(tmp_path: Path) -> dict[str, object]:
    artifacts = _burn_in_artifacts(tmp_path)
    assert len(artifacts) == 1
    return json.loads(artifacts[0].read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Test 1: ready_for_live when consecutive threshold met
# ---------------------------------------------------------------------------


class TestReadyForLiveWhenConsecutiveThresholdMet:
    def test_ready_for_live_when_consecutive_threshold_met(self, monkeypatch, tmp_path: Path) -> None:
        export_dir = tmp_path / "local" / "exports" / "daily_paper_trading"
        today = _real_dt.date(2026, 5, 20)
        for i in range(10):
            d = today - _real_dt.timedelta(days=9 - i)
            _write_artifact(export_dir, d.strftime("%Y%m%d"), "130000", "ok")

        rc = _run_main_at_now(
            monkeypatch,
            tmp_path,
            extra_args=["--min-consecutive-days", "10"],
        )
        assert rc == 0

        data = _load_single_burn_in_artifact(tmp_path)
        assert data["ready_for_live"] is True
        assert data["consecutive_successes"] >= 10


# ---------------------------------------------------------------------------
# Test 2: not ready when below consecutive threshold
# ---------------------------------------------------------------------------


class TestNotReadyWhenBelowConsecutiveThreshold:
    def test_not_ready_when_below_consecutive_threshold(self, monkeypatch, tmp_path: Path) -> None:
        export_dir = tmp_path / "local" / "exports" / "daily_paper_trading"
        today = _real_dt.date(2026, 5, 20)
        for i in range(5):
            d = today - _real_dt.timedelta(days=4 - i)
            _write_artifact(export_dir, d.strftime("%Y%m%d"), "130000", "ok")

        rc = _run_main_at_now(
            monkeypatch,
            tmp_path,
            extra_args=["--min-consecutive-days", "10"],
        )
        assert rc == 0

        data = _load_single_burn_in_artifact(tmp_path)
        assert data["ready_for_live"] is False
        assert data["consecutive_successes"] == 5


# ---------------------------------------------------------------------------
# Test 3: not ready when failure rate exceeded
# ---------------------------------------------------------------------------


class TestNotReadyWhenFailureRateExceeded:
    def test_not_ready_when_failure_rate_exceeded(self, monkeypatch, tmp_path: Path) -> None:
        export_dir = tmp_path / "local" / "exports" / "daily_paper_trading"
        today = _real_dt.date(2026, 5, 20)
        # Write a failure on day 0 of the window, then 9 ok runs after it.
        failed_date = today - _real_dt.timedelta(days=9)
        _write_artifact(
            export_dir, failed_date.strftime("%Y%m%d"), "120000", "failed", failed_step="07_submit_ibkr_orders"
        )
        for i in range(1, 10):
            d = today - _real_dt.timedelta(days=9 - i)
            _write_artifact(export_dir, d.strftime("%Y%m%d"), "130000", "ok")

        rc = _run_main_at_now(
            monkeypatch,
            tmp_path,
            extra_args=["--min-consecutive-days", "5", "--max-failure-rate-pct", "0.0"],
        )
        assert rc == 0

        data = _load_single_burn_in_artifact(tmp_path)
        assert data["ready_for_live"] is False
        assert data["failed_runs"] >= 1
        assert data["failure_rate_pct"] > 0.0


# ---------------------------------------------------------------------------
# Test 4: dedup guard skips when already done
# ---------------------------------------------------------------------------


class TestDedupGuardSkipsWhenAlreadyDone:
    def test_dedup_guard_skips_when_already_done(self, monkeypatch, job_root: Path, capsys) -> None:
        mod = _mod()
        today_tag = "20260520"
        sentinel_log = job_root / "local" / "logs" / f"check_burn_in_status_{today_tag}_120000.log"
        sentinel_log.write_text(f"previous run\n{mod.COMPLETE_SENTINEL}\n", encoding="utf-8")

        rc = _run_main_at_now(
            monkeypatch,
            job_root,
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "skipping" in out.lower() or "already" in out.lower()

        # No new artifact should have been written.
        assert _burn_in_artifacts(job_root) == []


# ---------------------------------------------------------------------------
# Test 5: force-run bypasses dedup guard
# ---------------------------------------------------------------------------


class TestForceRunBypassesDedupGuard:
    def test_force_run_bypasses_dedup_guard(self, monkeypatch, job_root: Path) -> None:
        mod = _mod()
        today_tag = "20260520"
        sentinel_log = job_root / "local" / "logs" / f"check_burn_in_status_{today_tag}_120000.log"
        sentinel_log.write_text(f"previous run\n{mod.COMPLETE_SENTINEL}\n", encoding="utf-8")

        rc = _run_main_at_now(
            monkeypatch,
            job_root,
            extra_args=["--force-run"],
        )
        assert rc == 0

        # Artifact must have been written (job actually ran).
        assert len(_burn_in_artifacts(job_root)) == 1


# ---------------------------------------------------------------------------
# Test 6: no artifacts gives zero consecutive successes
# ---------------------------------------------------------------------------


class TestNoArtifactsGivesZeroConsecutiveSuccesses:
    def test_no_artifacts_gives_zero_consecutive_successes(self, monkeypatch, tmp_path: Path) -> None:
        rc = _run_main_at_now(
            monkeypatch,
            tmp_path,
        )
        assert rc == 0

        data = _load_single_burn_in_artifact(tmp_path)
        assert data["ready_for_live"] is False
        assert data["consecutive_successes"] == 0
        assert data["total_runs_in_window"] == 0


# ---------------------------------------------------------------------------
# Test 7: latest artifact used when multiple on same date
# ---------------------------------------------------------------------------


class TestLatestArtifactUsedWhenMultipleOnSameDate:
    def test_latest_artifact_used_when_multiple_on_same_date(self, monkeypatch, tmp_path: Path) -> None:
        export_dir = tmp_path / "local" / "exports" / "daily_paper_trading"
        today = _real_dt.date(2026, 5, 20)
        date_str = today.strftime("%Y%m%d")

        # Earlier artifact: ok; later artifact (higher time): failed.
        _write_artifact(export_dir, date_str, "120000", "ok")
        _write_artifact(export_dir, date_str, "150000", "failed", failed_step="07_submit_ibkr_orders")

        rc = _run_main_at_now(
            monkeypatch,
            tmp_path,
            fake_now=_real_dt.datetime(2026, 5, 20, 16, 0, 0),
        )
        assert rc == 0

        data = _load_single_burn_in_artifact(tmp_path)
        # Only one entry for the date, and it should be the later (failed) one.
        assert data["total_runs_in_window"] == 1
        assert data["entries"][0]["status"] == "failed"
        assert data["entries"][0]["artifact_file"].endswith("150000.json")
