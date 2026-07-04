"""Tests for scripts.checks.repo.secret_hygiene_check."""

from __future__ import annotations

from pathlib import Path

from common.paths.repo_paths import get_repo_root
from scripts.checks.repo.secret_hygiene_check import check_file, discover_files, run_secret_hygiene_check


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_python_secret_assignment_is_reported(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "src/example.py",
        "from __future__ import annotations\n\nAPI_KEY = 'abc123456789'\n",
    )

    assert check_file(path).problems == ["line 3: constant assigned to sensitive name `API_KEY`"]


def test_python_placeholder_secret_is_allowed(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "src/example.py",
        "from __future__ import annotations\n\nAPI_KEY = 'your-api-key'\n",
    )

    assert check_file(path).problems == []


def test_python_env_lookup_is_allowed(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "src/example.py",
        "from __future__ import annotations\n\nimport os\n\nAPI_KEY = os.getenv('API_KEY')\n",
    )

    assert check_file(path).problems == []


def test_env_var_name_constant_is_allowed(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "src/example.py",
        "from __future__ import annotations\n\n_NEWS_API_KEY_ENV = 'NEWS_API_KEY'\n",
    )

    assert check_file(path).problems == []


def test_text_secret_assignment_is_reported(tmp_path: Path) -> None:
    path = _write(tmp_path / ".github/workflows/example.yml", "token: abc123456789\n")

    assert check_file(path).problems == ["line 1: literal value assigned to sensitive name `token`"]


def test_env_example_is_not_discovered(tmp_path: Path) -> None:
    _write(tmp_path / ".env.example", "API_KEY=your-api-key\n")
    _write(tmp_path / "src/example.py", "from __future__ import annotations\n")

    discovered = {path.relative_to(tmp_path).as_posix() for path in discover_files(tmp_path)}

    assert ".env.example" not in discovered


def test_real_repo_secret_hygiene_is_clean() -> None:
    repo_root = get_repo_root(Path(__file__))

    assert run_secret_hygiene_check(repo_root, enforce=True) == 0
