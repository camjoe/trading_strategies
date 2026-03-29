from __future__ import annotations

import argparse
from pathlib import Path

from common.repo_paths import get_repo_root
from scripts.documentation_ui.api.check import run_api_reference_check
from scripts.documentation_ui.software.check import run_software_reference_check
from scripts.documentation_ui.finance.check import run_term_definitions_check


def run_reference_docs_check(
    repo_root: Path,
    include_terms: bool = True,
    include_software: bool = True,
    include_api: bool = True,
) -> int:
    if include_terms:
        term_exit = run_term_definitions_check(repo_root=repo_root)
        if term_exit != 0:
            return term_exit

    if include_software:
        software_exit = run_software_reference_check(repo_root=repo_root)
        if software_exit != 0:
            return software_exit

    if include_api:
        api_exit = run_api_reference_check(repo_root=repo_root)
        if api_exit != 0:
            return api_exit

    print("\nReference documentation checks completed successfully.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Financial & Market, Software, and API reference documentation sync checks.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--skip-terms", action="store_true", help="Skip the Financial & Market terms check.")
    parser.add_argument("--skip-software", action="store_true", help="Skip the Software reference check.")
    parser.add_argument("--skip-api", action="store_true", help="Skip the API reference check.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_reference_docs_check(
        repo_root=repo_root,
        include_terms=not args.skip_terms,
        include_software=not args.skip_software,
        include_api=not args.skip_api,
    )


if __name__ == "__main__":
    raise SystemExit(main())