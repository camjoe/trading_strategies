from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from common.paths.repo_paths import get_repo_root

from scripts.checks._runner import CheckStep, resolve_python_exe, run_check_steps
from scripts.checks.python.mypy_check import run_mypy
from scripts.checks.python.pytest_check import run_pytest
from scripts.checks.python.public_api_test_evidence_check import run_public_api_test_evidence_check
from scripts.checks.python.python_conventions_check import run_python_conventions_check
from scripts.checks.python.ruff_check import run_ruff
from scripts.checks.run_suite import run_suite_targeted


def run_python_check(
    repo_root: Path,
    python_exe: str,
    *,
    suite_names: list[str] | None = None,
    suite_changed: bool = False,
    suite_base: str | None = None,
    no_cov: bool = False,
    quiet: bool = True,
) -> int:
    """Run Python style, type, and test checks."""
    use_suite_targeting = bool(suite_names or suite_changed or suite_base)
    pytest_args = ["--no-cov"] if no_cov else None

    try:
        exit_code = run_check_steps(
            [
                CheckStep(
                    "Python conventions",
                    lambda: run_python_conventions_check(repo_root=repo_root, quiet=quiet, enforce=True),
                ),
                CheckStep(
                    "Public API test evidence",
                    lambda: run_public_api_test_evidence_check(
                        repo_root=repo_root,
                        base_ref=suite_base,
                        quiet=quiet,
                    ),
                ),
                CheckStep("Ruff", lambda: run_ruff(repo_root=repo_root, python_exe=python_exe)),
                CheckStep("Mypy", lambda: run_mypy(repo_root=repo_root, python_exe=python_exe)),
            ]
        )
        if exit_code != 0:
            return exit_code

        if use_suite_targeting:
            run_suite_targeted(
                repo_root=repo_root,
                python_exe=python_exe,
                suite_names=suite_names,
                changed=suite_changed,
                base_ref=suite_base,
                extra_args=pytest_args,
            )
        else:
            run_pytest(repo_root=repo_root, python_exe=python_exe, pytest_args=pytest_args)
    except subprocess.CalledProcessError as exc:
        print(f"\nStep failed with exit code {exc.returncode}: {' '.join(exc.cmd)}")
        return exc.returncode

    print("\nPython checks completed successfully.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Python style, type, and test checks.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
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
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show full clean-check output instead of compact PASS lines.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    python_exe = resolve_python_exe(repo_root)
    return run_python_check(
        repo_root=repo_root,
        python_exe=python_exe,
        suite_names=args.suite_names,
        suite_changed=args.suite_changed,
        suite_base=args.suite_base,
        no_cov=args.no_cov,
        quiet=not args.verbose,
    )


if __name__ == "__main__":
    raise SystemExit(main())
