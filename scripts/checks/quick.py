from __future__ import annotations

import argparse
from pathlib import Path

from common.paths.repo_paths import get_repo_root

from scripts.checks._runner import CheckStep, resolve_npm_exe, resolve_python_exe, run_check_steps, run_step
from scripts.checks.python_check import run_python_check
from scripts.checks.repo_check import run_repo_check


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fast day-to-day checks: repository checks plus Python checks.",
    )
    parser.add_argument(
        "--with-frontend",
        action="store_true",
        help="Also run frontend lint/typecheck/tests.",
    )
    parser.add_argument(
        "--suite",
        nargs="+",
        metavar="SUITE",
        dest="suite_names",
        default=None,
        help="Run only the specified test suite(s) instead of the full suite.",
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        dest="suite_changed",
        help="Run only suites with uncommitted changed files (staged + unstaged).",
    )
    parser.add_argument(
        "--base",
        metavar="REF",
        dest="suite_base",
        default=None,
        help="Run only suites with changes vs a git ref (e.g. 'main', 'origin/main').",
    )
    parser.add_argument(
        "--no-cov",
        action="store_true",
        help="Disable coverage for faster targeted test runs.",
    )
    return parser.parse_args()


def _run_frontend_quick(frontend_dir: Path) -> None:
    npm_exe = resolve_npm_exe()
    run_step("Frontend quality: lint", [npm_exe, "run", "lint"], frontend_dir)
    run_step("Frontend quality: typecheck", [npm_exe, "run", "typecheck"], frontend_dir)
    run_step("Frontend tests: coverage", [npm_exe, "run", "test:coverage"], frontend_dir)


def run_quick(
    repo_root: Path,
    python_exe: str,
    with_frontend: bool = False,
    suite_names: list[str] | None = None,
    suite_changed: bool = False,
    suite_base: str | None = None,
    no_cov: bool = False,
) -> int:
    """Run quick checks for normal local development."""
    exit_code = run_check_steps(
        [
            CheckStep("Repository checks", lambda: run_repo_check(repo_root=repo_root)),
            CheckStep(
                "Python checks",
                lambda: run_python_check(
                    repo_root=repo_root,
                    python_exe=python_exe,
                    suite_names=suite_names,
                    suite_changed=suite_changed,
                    suite_base=suite_base,
                    no_cov=no_cov,
                ),
            ),
        ]
    )
    if exit_code != 0:
        return exit_code

    if with_frontend:
        frontend_dir = repo_root / "apps" / "paper_trading_web" / "frontend"
        _run_frontend_quick(frontend_dir)

    print("\nQuick checks completed successfully.")
    return 0


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root(__file__)
    python_exe = resolve_python_exe(repo_root)

    return run_quick(
        repo_root=repo_root,
        python_exe=python_exe,
        with_frontend=args.with_frontend,
        suite_names=args.suite_names,
        suite_changed=args.suite_changed,
        suite_base=args.suite_base,
        no_cov=args.no_cov,
    )


if __name__ == "__main__":
    raise SystemExit(main())
