from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from common.paths.repo_paths import get_repo_root

from scripts.checks.layer_check import run_layer_check
from scripts.checks.mypy_check import run_mypy
from scripts.checks.pytest_check import run_pytest
from scripts.checks.readme_check import run_readme_consistency
from scripts.checks.run_suite import run_suite_targeted
from scripts.checks.ruff_check import run_ruff
from scripts.documentation_ui.check import run_reference_docs_check
from scripts.checks.shared import resolve_npm_exe, resolve_python_exe, run_step


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fast day-to-day checks: README consistency, mypy, and pytest (optional frontend).",
    )
    parser.add_argument(
        "--readme-max-age-days",
        type=int,
        default=90,
        help="Max README age in days for advisory consistency check.",
    )
    parser.add_argument(
        "--with-frontend",
        action="store_true",
        help="Also run frontend lint/typecheck/tests.",
    )
    parser.add_argument(
        "--with-reference-doc-checks",
        action="store_true",
        help="Also run all Financial & Market, Software, and API reference sync checks.",
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
    return parser.parse_args()


def _run_frontend_quick(frontend_dir: Path) -> None:
    npm_exe = resolve_npm_exe()
    run_step("Frontend quality: lint", [npm_exe, "run", "lint"], frontend_dir)
    run_step("Frontend quality: typecheck", [npm_exe, "run", "typecheck"], frontend_dir)
    run_step("Frontend tests: coverage", [npm_exe, "run", "test:coverage"], frontend_dir)


def run_quick(
    repo_root: Path,
    python_exe: str,
    readme_max_age_days: int = 90,
    with_frontend: bool = False,
    with_reference_doc_checks: bool = False,
    suite_names: list[str] | None = None,
    suite_changed: bool = False,
    suite_base: str | None = None,
) -> int:
    """Run quick checks. When suite targeting args are provided, only those
    test suites run instead of the full test suite."""
    use_suite_targeting = bool(suite_names or suite_changed or suite_base)
    try:
        run_readme_consistency(
            repo_root=repo_root,
            max_age_days=readme_max_age_days,
        )
        layer_exit = run_layer_check(repo_root=repo_root)
        if layer_exit != 0:
            return layer_exit
        if with_reference_doc_checks:
            reference_doc_exit = run_reference_docs_check(repo_root=repo_root)
            if reference_doc_exit != 0:
                return reference_doc_exit
        run_ruff(repo_root=repo_root, python_exe=python_exe)
        run_mypy(repo_root=repo_root, python_exe=python_exe)
        if use_suite_targeting:
            run_suite_targeted(
                repo_root=repo_root,
                python_exe=python_exe,
                suite_names=suite_names,
                changed=suite_changed,
                base_ref=suite_base,
            )
        else:
            run_pytest(repo_root=repo_root, python_exe=python_exe)

        if with_frontend:
            frontend_dir = repo_root / "apps" / "paper_trading_web" / "frontend"
            _run_frontend_quick(frontend_dir)
    except subprocess.CalledProcessError as exc:
        print(f"\nStep failed with exit code {exc.returncode}: {' '.join(exc.cmd)}")
        return exc.returncode

    print("\nQuick checks completed successfully.")
    return 0


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root(__file__)
    python_exe = resolve_python_exe(repo_root)

    return run_quick(
        repo_root=repo_root,
        python_exe=python_exe,
        readme_max_age_days=args.readme_max_age_days,
        with_frontend=args.with_frontend,
        with_reference_doc_checks=args.with_reference_doc_checks,
        suite_names=args.suite_names,
        suite_changed=args.suite_changed,
        suite_base=args.suite_base,
    )


if __name__ == "__main__":
    raise SystemExit(main())
