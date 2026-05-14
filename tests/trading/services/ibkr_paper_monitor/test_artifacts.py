"""Tests for IBKR paper account monitoring artifact reading."""

from __future__ import annotations

from pathlib import Path

import pytest

from trading.services.ibkr_paper_monitor import artifacts


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
    """Test that daily workflow status is parsed correctly from artifact."""
    artifact_dir = mock_repo_root / "local" / "exports" / "daily_paper_trading"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    artifact_file = artifact_dir / "daily_paper_trading_2026_05_10.json"
    artifact_data = {
        "success": True,
        "run_timestamp": "2026-05-10T09:30:00Z",
        "duration_seconds": 45.5,
        "failed_step": None,
        "steps": [
            {"name": "Load accounts", "status": "completed"},
            {"name": "Run sleeves", "status": "completed"},
            {"name": "Generate reports", "status": "completed"},
        ],
    }
    artifact_file.write_text(__import__("json").dumps(artifact_data))

    result = artifacts.fetch_daily_workflow_status(repo_root=mock_repo_root)

    assert result["status"] == "success"
    assert result["latest_run_time"] == "2026-05-10T09:30:00Z"
    assert result["duration_seconds"] == 45.5
    assert result["completed_steps"] == 3
    assert result["failed_step"] is None


def test_fetch_daily_workflow_status_handles_failed_run(mock_repo_root: Path) -> None:
    """Test that failed run status is detected."""
    artifact_dir = mock_repo_root / "local" / "exports" / "daily_paper_trading"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    artifact_file = artifact_dir / "daily_paper_trading_2026_05_10.json"
    artifact_data = {
        "success": False,
        "run_timestamp": "2026-05-10T09:30:00Z",
        "duration_seconds": 10.2,
        "failed_step": "Run sleeves",
        "steps": [
            {"name": "Load accounts", "status": "completed"},
            {"name": "Run sleeves", "status": "failed"},
        ],
    }
    artifact_file.write_text(__import__("json").dumps(artifact_data))

    result = artifacts.fetch_daily_workflow_status(repo_root=mock_repo_root)

    assert result["status"] == "failed"
    assert result["failed_step"] == "Run sleeves"
    assert result["completed_steps"] == 1


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
    """Test that governance check status is parsed correctly."""
    export_dir = mock_repo_root / "local" / "exports"

    # Create W1 leaderboard artifact
    w1_dir = export_dir / "weekly_governance_2026_05_10"
    w1_dir.mkdir(parents=True, exist_ok=True)
    w1_artifact = w1_dir / "w1_leaderboard_2026_05_10.json"
    w1_artifact.write_text(
        __import__("json").dumps(
            {"success": True, "run_timestamp": "2026-05-10T10:00:00Z"}
        )
    )

    result = artifacts.fetch_governance_checks_status(repo_root=mock_repo_root)

    assert result["w1_leaderboard"]["status"] == "success"
    assert result["w1_leaderboard"]["last_run"] == "2026-05-10T10:00:00Z"


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
        "min_required_successes": 10,
        "check_time": "2026-05-10T16:00:00Z",
    }
    artifact_file.write_text(__import__("json").dumps(artifact_data))

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
        "min_required_successes": 10,
        "check_time": "2026-05-10T16:00:00Z",
    }
    artifact_file.write_text(__import__("json").dumps(artifact_data))

    result = artifacts.fetch_burn_in_status(repo_root=mock_repo_root)

    assert result["ready_for_live"] is False
    assert result["consecutive_successes"] == 5
    assert result["last_checked"] == "2026-05-10T16:00:00Z"
