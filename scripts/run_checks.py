from __future__ import annotations

import argparse

from common.paths.repo_paths import get_repo_root
from scripts.checks._runner import resolve_python_exe
from scripts.checks.ci import run_ci
from scripts.checks.docs.docs_check import run_docs_check
from scripts.checks.python.python_check import run_python_check
from scripts.checks.quick import run_quick
from scripts.checks.repo.repo_check import run_repo_check


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run aggregate repository checks.",
    )
    subparsers = parser.add_subparsers(dest="command")

    docs = subparsers.add_parser("docs", help="Run documentation drift and reference-doc checks.")
    docs.add_argument(
        "--readme-max-age-days",
        type=int,
        default=90,
        help="Max README age in days for consistency checks.",
    )
    docs.add_argument(
        "--advisory",
        action="store_true",
        help="Report enforce-capable documentation findings without failing.",
    )
    docs.add_argument(
        "--skip-reference-docs",
        action="store_true",
        help="Skip generated documentation UI asset checks.",
    )

    repo = subparsers.add_parser("repo", help="Run repository safety and structure checks.")
    repo.add_argument(
        "--advisory",
        action="store_true",
        help="Report enforce-capable repository findings without failing.",
    )

    python = subparsers.add_parser("python", help="Run Python style, type, and test checks.")
    _add_python_targeting_args(python)

    quick = subparsers.add_parser("quick", help="Run normal local checks: repo plus Python.")
    quick.add_argument("--with-frontend", action="store_true", help="Also run frontend lint/typecheck/tests.")
    _add_python_targeting_args(quick)

    ci = subparsers.add_parser("ci", help="Run CI-shaped checks: docs, repo, Python, and frontend.")
    ci.add_argument(
        "--readme-max-age-days",
        type=int,
        default=90,
        help="Max README age in days for consistency checks.",
    )
    ci.add_argument("--skip-frontend", action="store_true", help="Skip frontend checks.")

    parser.set_defaults(command="quick")
    return parser.parse_args()


def _add_python_targeting_args(parser: argparse.ArgumentParser) -> None:
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


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root(__file__)
    python_exe = resolve_python_exe(repo_root)

    if args.command == "docs":
        return run_docs_check(
            repo_root=repo_root,
            enforce=not args.advisory,
            quiet=True,
            readme_max_age_days=args.readme_max_age_days,
            include_reference_docs=not args.skip_reference_docs,
        )
    if args.command == "repo":
        return run_repo_check(repo_root=repo_root, enforce=not args.advisory)
    if args.command == "python":
        return run_python_check(
            repo_root=repo_root,
            python_exe=python_exe,
            suite_names=args.suite_names,
            suite_changed=args.suite_changed,
            suite_base=args.suite_base,
            no_cov=args.no_cov,
        )
    if args.command == "ci":
        return run_ci(
            repo_root=repo_root,
            python_exe=python_exe,
            skip_frontend=args.skip_frontend,
            readme_max_age_days=args.readme_max_age_days,
        )

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
