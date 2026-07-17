"""Tests for scripts.checks.run_suite — pure-logic functions only.

Subprocess-dependent functions (run_suite, _git_changed_files, main) are not
covered here because they require a live pytest process or a git repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.checks.run_suite import (
    _best_suite_for_file,
    _deduplicate_suites,
    _format_suite_listing,
    detect_suites_from_changes,
    discover_suites,
    resolve_targets,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_suite_tree(root: Path, *rel_dirs: str) -> None:
    """Create a tests/ directory tree with the given relative subdirs."""
    for rel in rel_dirs:
        (root / rel).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# discover_suites
# ---------------------------------------------------------------------------


class TestDiscoverSuites:
    def test_returns_sorted_suite_names(self, tmp_path: Path) -> None:
        _make_suite_tree(tmp_path, "trading/services", "trading/repositories", "apps/paper_trading_web")
        suites = discover_suites(tmp_path)
        assert suites == sorted(suites)

    def test_excludes_support_directory(self, tmp_path: Path) -> None:
        _make_suite_tree(tmp_path, "trading/services", "support/seed", "support/factories")
        suites = discover_suites(tmp_path)
        assert not any("support" in s for s in suites)

    def test_excludes_pycache_directories(self, tmp_path: Path) -> None:
        _make_suite_tree(tmp_path, "trading/services", "trading/__pycache__")
        suites = discover_suites(tmp_path)
        assert not any("__pycache__" in s for s in suites)

    def test_returns_nested_suites_at_all_levels(self, tmp_path: Path) -> None:
        _make_suite_tree(tmp_path, "trading/services/market_data")
        suites = discover_suites(tmp_path)
        assert "trading" in suites
        assert "trading/services" in suites
        assert "trading/services/market_data" in suites

    def test_empty_tree_returns_empty_list(self, tmp_path: Path) -> None:
        assert discover_suites(tmp_path) == []

    def test_uses_forward_slashes(self, tmp_path: Path) -> None:
        _make_suite_tree(tmp_path, "trading/services/market_data")
        suites = discover_suites(tmp_path)
        assert all("/" in s or len(Path(s).parts) == 1 for s in suites)
        assert not any("\\" in s for s in suites)


def test_suite_listing_is_cp1252_safe() -> None:
    listing = _format_suite_listing(["trading", "trading/services"])

    assert "all  ->  tests/" in listing
    listing.encode("cp1252")


# ---------------------------------------------------------------------------
# _deduplicate_suites
# ---------------------------------------------------------------------------


class TestDeduplicateSuites:
    def test_removes_child_when_parent_present(self) -> None:
        result = _deduplicate_suites(["trading/services", "trading/services/market_data"])
        assert result == ["trading/services"]

    def test_keeps_both_when_no_overlap(self) -> None:
        result = _deduplicate_suites(["trading/services", "apps/paper_trading_web"])
        assert set(result) == {"trading/services", "apps/paper_trading_web"}

    def test_removes_deep_child_with_grandparent_present(self) -> None:
        result = _deduplicate_suites(["trading", "trading/services/market_data"])
        assert result == ["trading"]

    def test_handles_exact_duplicate(self) -> None:
        result = _deduplicate_suites(["trading/services", "trading/services"])
        assert result == ["trading/services"]

    def test_empty_input_returns_empty(self) -> None:
        assert _deduplicate_suites([]) == []

    def test_single_item_is_unchanged(self) -> None:
        assert _deduplicate_suites(["trading/services"]) == ["trading/services"]

    def test_does_not_confuse_partial_name_prefix(self) -> None:
        # "trading/service" must NOT suppress "trading/services"
        result = _deduplicate_suites(["trading/service", "trading/services"])
        assert set(result) == {"trading/service", "trading/services"}


# ---------------------------------------------------------------------------
# _best_suite_for_file
# ---------------------------------------------------------------------------


class TestBestSuiteForFile:
    def test_test_file_maps_to_its_parent_suite(self, tmp_path: Path) -> None:
        _make_suite_tree(tmp_path, "trading/services/market_data")
        result = _best_suite_for_file("tests/trading/services/market_data/test_features.py", tmp_path)
        assert result == "trading/services/market_data"

    def test_test_file_directly_under_tests_root_returns_none(self, tmp_path: Path) -> None:
        result = _best_suite_for_file("tests/test_something.py", tmp_path)
        assert result is None

    def test_source_file_maps_to_matching_tests_mirror(self, tmp_path: Path) -> None:
        _make_suite_tree(tmp_path, "trading/services/market_data")
        result = _best_suite_for_file("trading/services/market_data/features.py", tmp_path)
        assert result == "trading/services/market_data"

    def test_source_file_walks_up_to_nearest_matching_suite(self, tmp_path: Path) -> None:
        # Only the parent dir has a tests mirror, not the specific subdir
        _make_suite_tree(tmp_path, "trading/services")
        result = _best_suite_for_file("trading/services/market_data/features.py", tmp_path)
        assert result == "trading/services"

    def test_source_file_with_no_match_returns_none(self, tmp_path: Path) -> None:
        result = _best_suite_for_file("some/unrelated/file.py", tmp_path)
        assert result is None

    def test_source_file_does_not_match_support_dir(self, tmp_path: Path) -> None:
        _make_suite_tree(tmp_path, "support/seed")
        result = _best_suite_for_file("support/seed/db.py", tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# resolve_targets
# ---------------------------------------------------------------------------


class TestResolveTargets:
    def test_all_alias_resolves_to_tests_root(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "repo"
        tests_root = repo_root / "tests"
        tests_root.mkdir(parents=True)

        result = resolve_targets(["all"], repo_root, tests_root)
        assert result == [tests_root]

    def test_valid_suite_name_resolves_to_directory(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "repo"
        suite_dir = repo_root / "tests" / "trading" / "services"
        suite_dir.mkdir(parents=True)
        tests_root = repo_root / "tests"

        result = resolve_targets(["trading/services"], repo_root, tests_root)
        assert result == [suite_dir]

    def test_valid_py_file_resolves_correctly(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "repo"
        test_file = repo_root / "tests" / "trading" / "test_something.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("# test\n", encoding="utf-8")
        tests_root = repo_root / "tests"

        result = resolve_targets(["trading/test_something.py"], repo_root, tests_root)
        assert result == [test_file.resolve()]

    def test_invalid_suite_raises_system_exit(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "repo"
        tests_root = repo_root / "tests"
        tests_root.mkdir(parents=True)

        with pytest.raises(SystemExit):
            resolve_targets(["nonexistent/suite"], repo_root, tests_root)

    def test_invalid_py_file_raises_system_exit(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "repo"
        tests_root = repo_root / "tests"
        tests_root.mkdir(parents=True)

        with pytest.raises(SystemExit):
            resolve_targets(["missing/test_file.py"], repo_root, tests_root)


# ---------------------------------------------------------------------------
# detect_suites_from_changes
# ---------------------------------------------------------------------------


class TestDetectSuitesFromChanges:
    def test_maps_changed_files_to_suites(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo_root = tmp_path / "repo"
        tests_root = repo_root / "tests"
        _make_suite_tree(tests_root, "trading/services/market_data")

        import scripts.checks.run_suite as run_suite_module

        monkeypatch.setattr(
            run_suite_module,
            "_git_changed_files",
            lambda *_a, **_kw: ["trading/services/market_data/features.py"],
        )

        result = detect_suites_from_changes(repo_root, tests_root)
        assert result == ["trading/services/market_data"]

    def test_deduplicates_overlapping_suites(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo_root = tmp_path / "repo"
        tests_root = repo_root / "tests"
        _make_suite_tree(tests_root, "trading/services", "trading/services/market_data")

        import scripts.checks.run_suite as run_suite_module

        monkeypatch.setattr(
            run_suite_module,
            "_git_changed_files",
            lambda *_a, **_kw: [
                "trading/services/accounts/queries.py",
                "trading/services/market_data/features.py",
            ],
        )

        result = detect_suites_from_changes(repo_root, tests_root)
        assert result == ["trading/services"]

    def test_empty_changed_files_returns_empty_list(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo_root = tmp_path / "repo"
        tests_root = repo_root / "tests"
        tests_root.mkdir(parents=True)

        import scripts.checks.run_suite as run_suite_module

        monkeypatch.setattr(run_suite_module, "_git_changed_files", lambda *_a, **_kw: [])

        result = detect_suites_from_changes(repo_root, tests_root)
        assert result == []

    def test_files_with_no_matching_suite_are_excluded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo_root = tmp_path / "repo"
        tests_root = repo_root / "tests"
        tests_root.mkdir(parents=True)

        import scripts.checks.run_suite as run_suite_module

        monkeypatch.setattr(
            run_suite_module,
            "_git_changed_files",
            lambda *_a, **_kw: ["README.md", "pyproject.toml"],
        )

        result = detect_suites_from_changes(repo_root, tests_root)
        assert result == []
