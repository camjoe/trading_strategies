"""Tests for autonomy monitoring artifact reading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading.services.autonomy_monitor import artifacts


@pytest.fixture
def mock_repo_root(tmp_path: Path) -> Path:
    """Create a temporary repo root with local/exports directory."""
    export_dir = tmp_path / "local" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_find_latest_artifact_returns_none_when_dir_missing(tmp_path: Path) -> None:
    """Test that None is returned when search directory doesn't exist."""
    result = artifacts._find_latest_artifact("*.json", tmp_path / "nonexistent")
    assert result is None


def test_find_latest_artifact_returns_none_when_no_matches(mock_repo_root: Path) -> None:
    """Test that None is returned when no files match pattern."""
    result = artifacts._find_latest_artifact("*.json", mock_repo_root / "local" / "exports")
    assert result is None


def test_find_latest_artifact_returns_latest_file(mock_repo_root: Path) -> None:
    """Test that the latest matching file is returned."""
    export_dir = mock_repo_root / "local" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    # Create multiple test files
    file1 = export_dir / "data_1.json"
    file2 = export_dir / "data_2.json"
    file3 = export_dir / "data_3.json"

    file1.write_text('{"value": 1}')
    file2.write_text('{"value": 2}')
    file3.write_text('{"value": 3}')

    result = artifacts._find_latest_artifact("data_*.json", export_dir)
    assert result is not None
    assert result["value"] == 3  # Latest file has value 3


def test_find_latest_artifact_returns_none_on_json_decode_error(mock_repo_root: Path) -> None:
    """Test that None is returned when JSON parsing fails."""
    export_dir = mock_repo_root / "local" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    bad_json = export_dir / "bad.json"
    bad_json.write_text("{invalid json}")

    result = artifacts._find_latest_artifact("bad.json", export_dir)
    assert result is None


def test_fetch_daily_workflow_status_returns_unknown_when_no_artifact(
    mock_repo_root: Path,
) -> None:
    """Test that unknown status is returned when no artifact exists."""
    result = artifacts.fetch_daily_workflow_status(repo_root=mock_repo_root)

    assert result["status"] == "unknown"
    assert result["latest_run_time"] is None
    assert result["step_results"] == []
    assert result["completed_steps"] == 0
    assert result["duration_seconds"] is None
    assert result["failed_step"] is None


def test_fetch_daily_workflow_status_parses_artifact(mock_repo_root: Path) -> None:
    """Reads the key names the daily workflow actually writes."""
    artifact_dir = mock_repo_root / "local" / "exports" / "daily_paper_trading"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    artifact_file = artifact_dir / "daily_paper_trading_20260510_093000.json"
    artifact_file.write_text(
        json.dumps(
            {
                "job": "daily_paper_trading",
                "status": "success",
                "started_at": "2026-05-10T09:30:00+00:00",
                "finished_at": "2026-05-10T09:30:45.500000+00:00",
                "step_results": [
                    {"step": "00_ingest_market_and_account", "status": "ok", "duration_seconds": 0.4},
                    {"step": "04_rotation_decision", "status": "skipped", "duration_seconds": None},
                    {"step": "05_build_position_targets_by_book", "status": "ok", "duration_seconds": 12.0},
                ],
                "completed_steps": [],
            }
        )
    )

    result = artifacts.fetch_daily_workflow_status(repo_root=mock_repo_root)

    assert result["status"] == "success"
    assert result["latest_run_time"] == "2026-05-10T09:30:45.500000+00:00"
    assert result["duration_seconds"] == pytest.approx(45.5)
    # A skipped step is a recorded decision, so it counts as reached-a-conclusion.
    assert result["completed_steps"] == 3
    assert result["failed_step"] is None


def test_fetch_daily_workflow_status_handles_failed_run(mock_repo_root: Path) -> None:
    """A failed run reports its status and the step that broke."""
    artifact_dir = mock_repo_root / "local" / "exports" / "daily_paper_trading"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    artifact_file = artifact_dir / "daily_paper_trading_20260510_093000.json"
    artifact_file.write_text(
        json.dumps(
            {
                "job": "daily_paper_trading",
                "status": "failed",
                "started_at": "2026-05-10T09:30:00+00:00",
                "finished_at": "2026-05-10T09:30:10+00:00",
                "failed_step": "07_submit_ibkr_orders",
                "step_results": [
                    {"step": "00_ingest_market_and_account", "status": "ok"},
                    {"step": "07_submit_ibkr_orders", "status": "failed"},
                ],
                "error": "broker refused connection",
            }
        )
    )

    result = artifacts.fetch_daily_workflow_status(repo_root=mock_repo_root)

    assert result["status"] == "failed"
    assert result["failed_step"] == "07_submit_ibkr_orders"
    assert result["completed_steps"] == 2


def test_fetch_daily_workflow_status_tolerates_unparseable_timestamps(mock_repo_root: Path) -> None:
    artifact_dir = mock_repo_root / "local" / "exports" / "daily_paper_trading"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "daily_paper_trading_20260510_093000.json").write_text(
        json.dumps({"status": "success", "started_at": "not-a-time", "finished_at": "nope", "step_results": []})
    )

    result = artifacts.fetch_daily_workflow_status(repo_root=mock_repo_root)

    assert result["status"] == "success"
    assert result["duration_seconds"] is None


def test_fetch_governance_checks_status_returns_defaults_when_no_artifacts(
    mock_repo_root: Path,
) -> None:
    """Test that default 'not_run' status is returned when no artifacts exist."""
    result = artifacts.fetch_governance_checks_status(repo_root=mock_repo_root)

    # Should have all 6 governance checks with not_run status
    assert "w1_leaderboard" in result
    assert "w2_promotion" in result
    assert "w3_allocation" in result
    assert "m1_risk_rebaseline" in result
    assert "m2_parameter_governance" in result
    assert "m3_performance_audit" in result

    for check in result.values():
        assert check["status"] == "not_run"
        assert check["last_run"] is None


def test_fetch_governance_checks_status_parses_artifacts(mock_repo_root: Path) -> None:
    """Governance artifacts live in local/artifacts as {job_name}_{tag}_{stamp}.json."""
    artifact_dir = mock_repo_root / "local" / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "weekly_governance_w1_leaderboard_2026_W19_20260510_100000.json").write_text(
        json.dumps({"week": "2026_W19", "generated_at": "2026-05-10T10:00:00+00:00", "accounts": []})
    )

    result = artifacts.fetch_governance_checks_status(repo_root=mock_repo_root)

    assert result["w1_leaderboard"]["status"] == "success"
    assert result["w1_leaderboard"]["last_run"] == "2026-05-10T10:00:00+00:00"
    assert result["w1_leaderboard"]["has_results"] is True
    # The other five remain unreported rather than defaulting to success.
    assert result["w2_promotion"]["status"] == "not_run"


def test_governance_job_names_do_not_cross_match(mock_repo_root: Path) -> None:
    """m1's artifact must not satisfy m2's lookup, and vice versa."""
    artifact_dir = mock_repo_root / "local" / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "monthly_governance_m2_parameter_governance_2026_05_20260510_100000.json").write_text(
        json.dumps({"generated_at": "2026-05-10T10:00:00+00:00"})
    )

    result = artifacts.fetch_governance_checks_status(repo_root=mock_repo_root)

    assert result["m2_parameter_governance"]["status"] == "success"
    assert result["m1_risk_rebaseline"]["status"] == "not_run"
    assert result["m3_performance_audit"]["status"] == "not_run"


def test_fetch_burn_in_status_returns_defaults_when_no_artifact(
    mock_repo_root: Path,
) -> None:
    """Test that default not-ready status is returned when no artifact exists."""
    result = artifacts.fetch_burn_in_status(repo_root=mock_repo_root)

    assert result["ready_for_live"] is False
    assert result["consecutive_successes"] == 0
    assert result["min_required_successes"] == 10
    assert result["last_checked"] is None


def test_fetch_burn_in_status_parses_artifact(mock_repo_root: Path) -> None:
    """Test that burn-in status is parsed correctly from artifact."""
    artifact_dir = mock_repo_root / "local" / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    artifact_file = artifact_dir / "check_burn_in_status_2026_05_10.json"
    artifact_data = {
        "ready_for_live": True,
        "consecutive_successes": 15,
        "min_consecutive_days": 10,
        "generated_at": "2026-05-10T16:00:00Z",
    }
    artifact_file.write_text(json.dumps(artifact_data))

    result = artifacts.fetch_burn_in_status(repo_root=mock_repo_root)

    assert result["ready_for_live"] is True
    assert result["consecutive_successes"] == 15
    assert result["min_required_successes"] == 10
    assert result["last_checked"] == "2026-05-10T16:00:00Z"


def test_fetch_burn_in_status_handles_not_ready(mock_repo_root: Path) -> None:
    """Test that not-ready status is handled correctly."""
    artifact_dir = mock_repo_root / "local" / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    artifact_file = artifact_dir / "check_burn_in_status_2026_05_10.json"
    artifact_data = {
        "ready_for_live": False,
        "consecutive_successes": 5,
        "min_consecutive_days": 10,
        "generated_at": "2026-05-10T16:00:00Z",
    }
    artifact_file.write_text(json.dumps(artifact_data))

    result = artifacts.fetch_burn_in_status(repo_root=mock_repo_root)

    assert result["ready_for_live"] is False
    assert result["consecutive_successes"] == 5
    assert result["last_checked"] == "2026-05-10T16:00:00Z"
