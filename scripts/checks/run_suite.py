"""Run a focused subset of the test suite by suite name or file path.

Suite names mirror the ``tests/`` directory tree, making them stable and
self-documenting.  Any subdirectory of ``tests/`` (excluding ``support/``) is
a valid suite name.  Individual ``.py`` test file paths are also accepted for
file-level targeting.

Usage::

    # List all available suite names
    python -m scripts.checks.run_suite --list

    # Run a top-level group
    python -m scripts.checks.run_suite trading/services

    # Run two suites together
    python -m scripts.checks.run_suite trading/services/market_data trading/services/promotion

    # Target a single test file
    python -m scripts.checks.run_suite trading/services/market_data/test_features.py

    # All tests
    python -m scripts.checks.run_suite all

    # Auto-detect suites from uncommitted changes (staged + unstaged)
    python -m scripts.checks.run_suite --changed

    # Auto-detect suites from changes vs a branch (PR workflow)
    python -m scripts.checks.run_suite --base main
    python -m scripts.checks.run_suite --base origin/main

    # Pass extra flags to pytest
    python -m scripts.checks.run_suite trading/services -v --no-cov
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from common.paths.repo_paths import get_repo_root

from scripts.checks.shared import resolve_python_exe

_EXCLUDED_DIRS = {"support", "__pycache__"}
_ALL_ALIAS = "all"


def discover_suites(tests_root: Path) -> list[str]:
    """Return all valid suite names, sorted, excluding support and cache dirs."""
    suites: list[str] = []
    for path in sorted(tests_root.rglob("*")):
        if not path.is_dir():
            continue
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            continue
        rel = path.relative_to(tests_root)
        suites.append(str(rel).replace("\\", "/"))
    return suites


def _git_changed_files(repo_root: Path, base_ref: str | None) -> list[str]:
    """Return a list of repo-relative changed file paths from git."""
    if base_ref:
        # Three-dot diff: all commits on current branch not on base_ref
        cmd = ["git", "diff", "--name-only", f"{base_ref}...HEAD"]
    else:
        # All uncommitted changes: staged + unstaged
        staged = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        unstaged = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        files = set((staged + unstaged).splitlines())
        return sorted(f for f in files if f)

    result = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return [f for f in result.stdout.splitlines() if f]


def _best_suite_for_file(rel_path: str, tests_root: Path) -> str | None:
    """Map a repo-relative file path to the deepest matching suite name.

    Strategy:
    1. If the file lives under ``tests/``, strip the prefix and use the
       parent directory as the suite (if it exists and is not excluded).
    2. Otherwise treat the file as source code and walk up its directory
       hierarchy looking for a matching ``tests/<dir>`` subtree.
    """
    parts = Path(rel_path).parts

    # File is already a test file
    if parts and parts[0] == "tests":
        test_rel = Path(*parts[1:]) if len(parts) > 1 else Path()
        candidate = tests_root / test_rel.parent
        # Walk up to the nearest real suite dir (not support/, not root)
        while candidate != tests_root:
            rel = candidate.relative_to(tests_root)
            if candidate.is_dir() and not any(p in _EXCLUDED_DIRS for p in rel.parts):
                return str(rel).replace("\\", "/")
            candidate = candidate.parent
        return None  # file is directly under tests/ root — not a targeted suite

    # Source file — find the deepest matching tests/ mirror directory
    # Walk from the file's full directory down to the repo root
    file_dir_parts = list(Path(rel_path).parent.parts)
    while file_dir_parts:
        candidate = tests_root / Path(*file_dir_parts)
        if candidate.is_dir() and not any(p in _EXCLUDED_DIRS for p in file_dir_parts):
            return "/".join(file_dir_parts)
        file_dir_parts.pop()

    return None


def _deduplicate_suites(suites: list[str]) -> list[str]:
    """Remove suites that are already covered by an ancestor suite in the list.

    If both ``trading/services`` and ``trading/services/market_data`` are
    present, the child is redundant — ``trading/services`` covers it.
    """
    sorted_suites = sorted(suites)
    kept: list[str] = []
    for suite in sorted_suites:
        # Keep this suite only if no already-kept suite is a prefix of it
        if not any(suite == kept_s or suite.startswith(kept_s + "/") for kept_s in kept):
            kept.append(suite)
    return kept


def detect_suites_from_changes(
    repo_root: Path,
    tests_root: Path,
    base_ref: str | None = None,
) -> list[str]:
    """Return deduplicated suite names inferred from git-changed files."""
    changed = _git_changed_files(repo_root, base_ref)
    if not changed:
        return []

    seen: set[str] = set()
    suites: list[str] = []
    for rel_path in changed:
        suite = _best_suite_for_file(rel_path, tests_root)
        if suite and suite not in seen:
            seen.add(suite)
            suites.append(suite)

    return _deduplicate_suites(sorted(suites))


def run_suite_targeted(
    repo_root: Path,
    python_exe: str,
    suite_names: list[str] | None = None,
    changed: bool = False,
    base_ref: str | None = None,
    extra_args: list[str] | None = None,
) -> None:
    """Run targeted tests; raise ``subprocess.CalledProcessError`` on failure.

    Handles all three selection modes:
    - Explicit ``suite_names``
    - ``changed=True`` for uncommitted changes
    - ``base_ref`` for diff vs a git ref

    Intended for use by other check scripts (e.g. ``quick.py``).
    """
    tests_root = repo_root / "tests"

    if changed or base_ref is not None:
        names = detect_suites_from_changes(repo_root, tests_root, base_ref=base_ref)
        if not names:
            source = f"vs {base_ref!r}" if base_ref else "in working tree"
            print(f"\n==> Python tests: no changed suites found {source} — skipping.")
            return
        label = f"--base {base_ref}" if base_ref else "--changed"
        print(f"Detected suites from {label}: {', '.join(names)}", flush=True)
    else:
        names = list(suite_names or [])

    if not names:
        raise ValueError("run_suite_targeted: no suite names provided")

    exit_code = run_suite(
        names, repo_root, python_exe, extra_args=["--override-ini", "addopts=-q -n auto", *(extra_args or [])]
    )
    if exit_code != 0:
        import subprocess

        raise subprocess.CalledProcessError(exit_code, ["pytest"])


def resolve_targets(names: list[str], repo_root: Path, tests_root: Path) -> list[Path]:
    """Resolve suite names and file paths to absolute ``Path`` objects.

    Raises ``SystemExit`` with an informative message on any invalid input.
    """
    resolved: list[Path] = []
    errors: list[str] = []

    for name in names:
        if name == _ALL_ALIAS:
            resolved.append(tests_root)
            continue

        # Individual test file path (ends in .py)
        if name.endswith(".py"):
            # Accept either absolute, repo-relative, or tests/-relative
            candidates = [
                Path(name),
                repo_root / name,
                tests_root / name,
            ]
            for candidate in candidates:
                try:
                    resolved_path = candidate.resolve()
                    if resolved_path.is_file():
                        resolved.append(resolved_path)
                        break
                except OSError:
                    continue
            else:
                errors.append(f"  '{name}' — file not found (tried repo-relative and tests/-relative paths)")
            continue

        # Directory suite name — treated as relative to tests/
        candidate = tests_root / name
        if candidate.is_dir():
            resolved.append(candidate)
        else:
            valid_examples = discover_suites(tests_root)[:6]
            errors.append(
                f"  '{name}' — no such suite directory under tests/\n"
                f"    Run --list to see all valid suite names.\n"
                f"    Examples: {', '.join(valid_examples)}"
            )

    if errors:
        print("run_suite: invalid suite(s) or file(s):\n" + "\n".join(errors), file=sys.stderr)
        raise SystemExit(1)

    return resolved


def run_suite(
    suite_names: list[str],
    repo_root: Path,
    python_exe: str,
    extra_args: list[str] | None = None,
) -> int:
    """Run pytest for the given suite names and return the exit code."""
    tests_root = repo_root / "tests"
    targets = resolve_targets(suite_names, repo_root, tests_root)
    command = [
        python_exe,
        "-m",
        "pytest",
        *(str(t) for t in targets),
        *(extra_args or []),
    ]
    label = ", ".join(suite_names)
    print(f"\n==> Python tests: suite [{label}]", flush=True)
    result = subprocess.run(command, cwd=str(repo_root))
    return result.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a focused subset of the test suite by suite name or file path.\n\n"
            "Suite names mirror the tests/ directory tree (e.g. 'trading/services',\n"
            "'trading/services/market_data').  Use 'all' to run the full suite.\n"
            "Individual .py file paths are also accepted.\n\n"
            "Use --changed or --base to auto-detect suites from git-changed files."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m scripts.checks.run_suite --list\n"
            "  python -m scripts.checks.run_suite all\n"
            "  python -m scripts.checks.run_suite trading/services\n"
            "  python -m scripts.checks.run_suite trading/services/market_data trading/services/promotion\n"
            "  python -m scripts.checks.run_suite trading/services/market_data/test_features.py\n"
            "  python -m scripts.checks.run_suite --changed\n"
            "  python -m scripts.checks.run_suite --base main\n"
            "  python -m scripts.checks.run_suite trading/services -v --no-cov\n"
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available suite names and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print which suites would run without actually running them. "
            "Works with explicit suite names, --changed, and --base."
        ),
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help=(
            "Auto-detect suites from uncommitted changes (staged + unstaged). "
            "Mutually exclusive with explicit suite names."
        ),
    )
    parser.add_argument(
        "--base",
        metavar="REF",
        default=None,
        help=(
            "Auto-detect suites from changes vs a git ref (e.g. 'main', 'origin/main'). "
            "Uses a three-dot diff: all commits on HEAD not on REF. "
            "Mutually exclusive with explicit suite names."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to auto-detected workspace root.",
    )
    parser.add_argument(
        "suites",
        nargs="*",
        help="Suite names or .py file paths to run.",
    )
    # parse_known_args lets unrecognized flags (e.g. --no-cov, -v) pass through
    # to pytest regardless of where they appear on the command line.
    return parser.parse_known_args()


def main() -> int:
    args, pytest_passthrough = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    tests_root = repo_root / "tests"

    if args.list:
        suites = discover_suites(tests_root)
        print(f"Available suites ({len(suites)} total):\n")
        print("  all  →  tests/  (entire test suite)\n")
        for suite in suites:
            print(f"  {suite}")
        return 0

    # Separate suite names from pytest pass-through args.
    suite_names: list[str] = []
    pytest_extra: list[str] = []
    dry_run = args.dry_run
    for token in list(args.suites or []) + list(pytest_passthrough or []):
        if token == "--dry-run":
            dry_run = True
        elif token.startswith("-"):
            pytest_extra.append(token)
        else:
            suite_names.append(token)

    auto_detect = args.changed or args.base is not None

    if auto_detect and suite_names:
        print(
            "run_suite: cannot combine --changed/--base with explicit suite names.",
            file=sys.stderr,
        )
        return 1

    if auto_detect:
        base_ref = args.base  # None means uncommitted-only
        suite_names = detect_suites_from_changes(repo_root, tests_root, base_ref=base_ref)
        if not suite_names:
            source = f"vs {base_ref!r}" if base_ref else "in working tree"
            print(f"run_suite: no changed files with matching test suites found {source}.")
            return 0
        label = f"--base {args.base}" if args.base else "--changed"
        print(f"Detected suites from {label}: {', '.join(suite_names)}")
    else:
        suite_names = _deduplicate_suites(suite_names)

    if not suite_names:
        print(
            "run_suite: no suite specified.\n"
            "  Use --list to see available suites, or pass 'all' to run everything.\n"
            "  Use --changed to auto-detect suites from uncommitted changes.\n"
            "  Use --base <ref> to auto-detect from changes vs a branch.\n"
            "  Example: python -m scripts.checks.run_suite trading/services",
            file=sys.stderr,
        )
        return 1

    if args.dry_run or dry_run:
        print(f"Suites that would run ({len(suite_names)}):")
        for name in suite_names:
            print(f"  {name}")
        return 0

    python_exe = resolve_python_exe(repo_root)
    return run_suite(
        suite_names=suite_names,
        repo_root=repo_root,
        python_exe=python_exe,
        extra_args=pytest_extra,
    )


if __name__ == "__main__":
    raise SystemExit(main())
