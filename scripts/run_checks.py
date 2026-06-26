from __future__ import annotations

import argparse

from common.paths.repo_paths import get_repo_root

from scripts.checks.ci import run_ci
from scripts.checks.quick import run_quick
from scripts.checks.shared import resolve_python_exe


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Unified check runner. Use --profile quick for day-to-day checks "
            "or --profile ci for CI-shaped smoke validation."
        ),
    )
    parser.add_argument(
        "--profile",
        choices=("quick", "ci"),
        default="quick",
        help="Check profile to run.",
    )
    parser.add_argument(
        "--readme-max-age-days",
        type=int,
        default=90,
        help="Max README age in days for consistency checks.",
    )

    # Quick profile option
    parser.add_argument(
        "--with-frontend",
        action="store_true",
        help="Quick profile: also run frontend lint/typecheck/tests.",
    )
    parser.add_argument(
        "--with-reference-doc-checks",
        action="store_true",
        help="Quick/CI profile: run Financial & Market, Software, and API reference sync checks.",
    )
    parser.add_argument(
        "--suite",
        nargs="+",
        metavar="SUITE",
        dest="suite_names",
        default=None,
        help="Quick profile: run only the specified test suite(s) instead of the full suite.",
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        dest="suite_changed",
        help="Quick profile: run only suites with uncommitted changed files (staged + unstaged).",
    )
    parser.add_argument(
        "--base",
        metavar="REF",
        dest="suite_base",
        default=None,
        help="Quick profile: run only suites with changes vs a git ref (e.g. 'main', 'origin/main').",
    )

    # CI profile options
    parser.add_argument("--skip-python", action="store_true", help="CI profile: skip Python checks.")
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="CI profile: skip frontend checks.",
    )
    parser.add_argument(
        "--skip-readme-consistency",
        action="store_true",
        help="CI profile: skip README consistency check.",
    )
    parser.add_argument(
        "--skip-maps-check",
        action="store_true",
        help="CI profile: skip maps drift check.",
    )
    parser.add_argument(
        "--skip-link-check",
        action="store_true",
        help="CI profile: skip doc link check.",
    )
    parser.add_argument(
        "--skip-module-ref-check",
        action="store_true",
        help="CI profile: skip doc `-m` module reference check.",
    )
    parser.add_argument(
        "--install-python-tools",
        action="store_true",
        help="CI profile: install ruff and mypy before quality gates.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root(__file__)
    python_exe = resolve_python_exe(repo_root)

    if args.profile == "quick":
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

    return run_ci(
        repo_root=repo_root,
        python_exe=python_exe,
        skip_python=args.skip_python,
        skip_frontend=args.skip_frontend,
        skip_readme_consistency=args.skip_readme_consistency,
        skip_maps_check=args.skip_maps_check,
        skip_link_check=args.skip_link_check,
        skip_module_ref_check=args.skip_module_ref_check,
        readme_max_age_days=args.readme_max_age_days,
        install_python_tools=args.install_python_tools,
        with_reference_doc_checks=args.with_reference_doc_checks,
    )


if __name__ == "__main__":
    raise SystemExit(main())
