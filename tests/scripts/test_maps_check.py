from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.checks.docs.maps_check import (
    CODE_SPAN_RE,
    HEADER_PATH_RE,
    HEADER_RE,
    PY_PATH_RE,
    SUBSECTION_RE,
    _extract_documented_paths,
    _heading_path,
    _is_full_path,
    _resolve_token,
    check_map,
    run_maps_check,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, content: str = "x = 1\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Regex unit tests
# ---------------------------------------------------------------------------


def test_code_span_re_captures_each_backtick_span() -> None:
    assert CODE_SPAN_RE.findall("see `a/b.py` and `c.py`") == ["a/b.py", "c.py"]


def test_py_path_re_accepts_paths_and_rejects_prose() -> None:
    assert PY_PATH_RE.match("accounts/queries.py")
    assert PY_PATH_RE.match("db.py")
    assert PY_PATH_RE.match("a/b/c-d.py")
    assert not PY_PATH_RE.match("python -m scripts.run_checks")  # has spaces
    assert not PY_PATH_RE.match("notes.md")  # not a .py


def test_header_re_captures_heading_text_only() -> None:
    match = HEADER_RE.match("### `trading/services/`")
    assert match is not None
    assert match.group(1) == "###"  # leading hashes -> heading level
    assert match.group(2) == "`trading/services/`"
    assert HEADER_RE.match("not a heading") is None


def test_header_path_re_drops_trailing_slash() -> None:
    match = HEADER_PATH_RE.search("### `trading/services/` (a layer)")
    assert match is not None
    assert match.group(1) == "trading/services"


def test_subsection_re_captures_parenthetical_dir() -> None:
    match = SUBSECTION_RE.search("**Runtime jobs** (`trading/interfaces/runtime/jobs/`)")
    assert match is not None
    assert match.group(1) == "trading/interfaces/runtime/jobs"
    assert SUBSECTION_RE.search("**Bold label** with no directory") is None


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def test_heading_path_extracts_first_backtick_path() -> None:
    assert _heading_path("`trading/domain/`") == "trading/domain"
    assert _heading_path("Routes (`routes/`)") == "routes"  # relative subsection path
    assert _heading_path("Layered Backbone") is None  # no backtick path


def test_is_full_path() -> None:
    assert _is_full_path("src/trading/domain")
    assert _is_full_path("apps/paper_trading_web/backend")
    assert not _is_full_path("routes")  # section-relative
    assert not _is_full_path("trading/domain")  # first-party packages now live under src/


def test_resolve_token_full_path_vs_section_relative() -> None:
    assert _resolve_token("src/trading/models/x.py", "ignored") == "src/trading/models/x.py"
    assert _resolve_token("accounting.py", "src/trading/domain") == "src/trading/domain/accounting.py"
    assert _resolve_token("a/b.py", "src/trading/services") == "src/trading/services/a/b.py"


# ---------------------------------------------------------------------------
# Core extraction — the regressions that motivated section-aware matching
# ---------------------------------------------------------------------------


def test_extract_is_section_aware_no_basename_collision() -> None:
    markdown = (
        "### `src/trading/domain/`\n"
        "| Module | Responsibility |\n"
        "| `accounting.py` | domain accounting |\n"
        "### `src/trading/services/`\n"
        "| `accounts/queries.py` | account reads |\n"
    )
    documented = _extract_documented_paths(markdown, "src/trading")
    assert "src/trading/domain/accounting.py" in documented
    assert "src/trading/services/accounts/queries.py" in documented
    # A bare `accounting.py` under domain must NOT count a same-named file elsewhere as documented.
    assert "src/trading/services/sleeves/accounting.py" not in documented


def test_extract_ignores_prose_mentions() -> None:
    markdown = (
        "### `src/trading/database/`\n"
        "Only repositories and the `runtime_loader.py` exception import from here.\n"
        "| `init.py` | initialise the schema |\n"
    )
    documented = _extract_documented_paths(markdown, "src/trading")
    assert "src/trading/database/init.py" in documented  # table row counts
    assert "src/trading/database/runtime_loader.py" not in documented  # prose mention does not


def test_extract_resolves_subsection_directories() -> None:
    markdown = (
        "### `src/trading/interfaces/`\n"
        "**Runtime jobs** (`src/trading/interfaces/runtime/jobs/`)\n"
        "| `daily/snapshot.py` | snapshot job |\n"
    )
    documented = _extract_documented_paths(markdown, "src/trading")
    assert "src/trading/interfaces/runtime/jobs/daily/snapshot.py" in documented


def test_extract_resolves_relative_subsection_under_full_section() -> None:
    """ui-map style: a relative `### Routes (`routes/`)` under a full-path `## Backend (...)`."""
    markdown = (
        "## Backend (`apps/paper_trading_web/backend/`)\n### Routes (`routes/`)\n| `accounts.py` | account routes |\n"
    )
    documented = _extract_documented_paths(markdown, "apps/paper_trading_web/backend")
    assert "apps/paper_trading_web/backend/routes/accounts.py" in documented


# ---------------------------------------------------------------------------
# check_map on a synthetic repo
# ---------------------------------------------------------------------------


def test_check_map_flags_undocumented_and_stale(tmp_path: Path) -> None:
    _write(tmp_path / "src/trading/domain/accounting.py")
    _write(tmp_path / "src/trading/services/sleeves/accounting.py")  # name collides, but undocumented
    _write(tmp_path / "src/trading/services/accounts/queries.py")
    _write(
        tmp_path / "map.md",
        "### `src/trading/domain/`\n"
        "| `accounting.py` | x |\n"
        "### `src/trading/services/`\n"
        "| `accounts/queries.py` | x |\n"
        "| `accounts/ghost.py` | x |\n",  # documented but no such file -> stale
    )

    report = check_map(tmp_path, "map.md", "src/trading", ())

    assert report.undocumented == ["src/trading/services/sleeves/accounting.py"]
    assert report.stale == ["src/trading/services/accounts/ghost.py"]


def test_check_map_respects_skip_subtrees(tmp_path: Path) -> None:
    _write(tmp_path / "src/trading/backtesting/backtest.py")
    _write(tmp_path / "src/trading/backtesting/domain/policy.py")  # under a dir-summarized subtree
    _write(tmp_path / "map.md", "### `src/trading/backtesting/`\n| `backtest.py` | x |\n")

    report = check_map(tmp_path, "map.md", "src/trading", ("src/trading/backtesting/domain",))

    assert report.undocumented == []  # policy.py is skipped, backtest.py is documented


# ---------------------------------------------------------------------------
# Real repo (advisory) + CLI exit codes
# ---------------------------------------------------------------------------


def test_run_maps_check_advisory_returns_zero_on_real_repo() -> None:
    """Advisory mode never fails the build, regardless of current drift."""
    assert run_maps_check(repo_root=PROJECT_ROOT) == 0


def test_cli_enforce_exits_nonzero_on_drift(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs/maps/trading-package-map.md", "### `src/trading/services/`\n| `accounts/queries.py` | x |\n"
    )
    _write(tmp_path / "src/trading/services/accounts/queries.py")
    _write(tmp_path / "src/trading/services/orphan.py")  # undocumented -> drift

    result = subprocess.run(
        [sys.executable, "-m", "scripts.checks.docs.maps_check", "--repo-root", str(tmp_path), "--enforce"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "orphan.py" in result.stdout
