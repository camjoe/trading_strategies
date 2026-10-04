"""Tests for scripts.checks.repo.path_safety_check."""

from __future__ import annotations

from pathlib import Path

from common.git import get_repo_root
from scripts.checks.repo.path_safety_check import check_file, run_path_safety_check
from tests.scripts.helpers import write_file


def test_os_path_join_is_reported(tmp_path: Path) -> None:
    path = write_file(
        tmp_path / "src/example.py",
        "from __future__ import annotations\n\nimport os\n\nvalue = os.path.join('a', 'b')\n",
    )

    assert check_file(path).problems == ["line 5: use pathlib.Path instead of os.path.join"]


def test_os_sep_is_reported(tmp_path: Path) -> None:
    path = write_file(
        tmp_path / "src/example.py",
        "from __future__ import annotations\n\nimport os\n\nvalue = 'a' + os.sep + 'b'\n",
    )

    assert check_file(path).problems == ["line 5: use pathlib/common path helpers instead of os.sep"]


def test_hardcoded_backslash_file_path_is_reported(tmp_path: Path) -> None:
    path = write_file(
        tmp_path / "src/example.py",
        "from __future__ import annotations\n\nvalue = 'local\\\\exports\\\\report.csv'\n",
    )

    assert check_file(path).problems == ["line 3: hardcoded backslash path string"]


def test_windows_task_name_is_allowed(tmp_path: Path) -> None:
    path = write_file(
        tmp_path / "src/example.py",
        "from __future__ import annotations\n\nvalue = 'Trading\\\\DailySnapshot'\n",
    )

    assert check_file(path).problems == []


def test_real_repo_path_safety_is_clean() -> None:
    repo_root = get_repo_root(Path(__file__))

    assert run_path_safety_check(repo_root, enforce=True) == 0
