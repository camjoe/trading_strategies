"""Tests for the migration chain integrity check."""

from __future__ import annotations

from pathlib import Path

from common.paths.repo_paths import get_repo_root
from scripts.checks.repo.migration_check import VERSIONS_DIR_REL, run_migration_check


def _write_revision(
    versions_dir: Path,
    file_name: str,
    *,
    revision: str,
    down_revision: str | None,
    upgrade_body: str = "    op.execute('CREATE TABLE t (id INTEGER)')",
    downgrade_body: str = "    op.execute('DROP TABLE t')",
    extra: str = "",
) -> None:
    down = f'"{down_revision}"' if down_revision is not None else "None"
    versions_dir.mkdir(parents=True, exist_ok=True)
    (versions_dir / file_name).write_text(
        f'''"""Synthetic revision."""

from __future__ import annotations

from alembic import op
{extra}

revision = "{revision}"
down_revision = {down}
branch_labels = None
depends_on = None


def upgrade() -> None:
{upgrade_body}


def downgrade() -> None:
{downgrade_body}
''',
        encoding="utf-8",
    )


def _versions_dir(tmp_path: Path) -> Path:
    return tmp_path / VERSIONS_DIR_REL


def test_real_repo_migration_chain_is_clean() -> None:
    assert run_migration_check(repo_root=get_repo_root(__file__)) == 0


def test_missing_versions_directory_fails(tmp_path: Path) -> None:
    assert run_migration_check(repo_root=tmp_path) == 1


def test_single_base_at_expected_head_passes(tmp_path: Path) -> None:
    _write_revision(_versions_dir(tmp_path), "0001_base.py", revision="0001", down_revision=None)
    assert run_migration_check(repo_root=tmp_path) == 0


def test_head_beyond_expected_constant_fails(tmp_path: Path, capsys) -> None:
    _write_revision(_versions_dir(tmp_path), "0001_base.py", revision="0001", down_revision=None)
    _write_revision(_versions_dir(tmp_path), "0002_next.py", revision="0002", down_revision="0001")
    assert run_migration_check(repo_root=tmp_path) == 1
    assert "EXPECTED_HEAD_REVISION" in capsys.readouterr().out


def test_empty_upgrade_fails(tmp_path: Path, capsys) -> None:
    _write_revision(
        _versions_dir(tmp_path),
        "0001_base.py",
        revision="0001",
        down_revision=None,
        upgrade_body="    pass",
    )
    assert run_migration_check(repo_root=tmp_path) == 1
    assert "upgrade() is missing or empty" in capsys.readouterr().out


def test_forbidden_application_import_fails(tmp_path: Path, capsys) -> None:
    _write_revision(
        _versions_dir(tmp_path),
        "0001_base.py",
        revision="0001",
        down_revision=None,
        extra="from infrastructure.database.backend import get_backend",
    )
    assert run_migration_check(repo_root=tmp_path) == 1
    assert "self-contained" in capsys.readouterr().out


def test_duplicate_revision_ids_fail(tmp_path: Path, capsys) -> None:
    _write_revision(_versions_dir(tmp_path), "0001_base.py", revision="0001", down_revision=None)
    _write_revision(_versions_dir(tmp_path), "0001_dupe.py", revision="0001", down_revision=None)
    assert run_migration_check(repo_root=tmp_path) == 1
    assert "duplicate revision id" in capsys.readouterr().out


def test_branched_chain_fails(tmp_path: Path, capsys) -> None:
    _write_revision(_versions_dir(tmp_path), "0001_base.py", revision="0001", down_revision=None)
    _write_revision(_versions_dir(tmp_path), "0002_a.py", revision="0002", down_revision="0001")
    _write_revision(_versions_dir(tmp_path), "0003_b.py", revision="0003", down_revision="0001")
    assert run_migration_check(repo_root=tmp_path) == 1
    assert "multiple children" in capsys.readouterr().out


def test_non_numeric_revision_fails(tmp_path: Path, capsys) -> None:
    _write_revision(_versions_dir(tmp_path), "abc_base.py", revision="abc1", down_revision=None)
    assert run_migration_check(repo_root=tmp_path) == 1
    assert "not 4-digit numeric" in capsys.readouterr().out


def test_advisory_mode_reports_without_failing(tmp_path: Path, capsys) -> None:
    _write_revision(
        _versions_dir(tmp_path),
        "0001_base.py",
        revision="0001",
        down_revision=None,
        upgrade_body="    pass",
    )
    assert run_migration_check(repo_root=tmp_path, enforce=False) == 0
    assert "WARN" in capsys.readouterr().out
