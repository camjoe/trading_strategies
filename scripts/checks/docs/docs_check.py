from __future__ import annotations

import argparse
from pathlib import Path

from common.git import get_repo_root
from scripts.checks._runner import CheckStep, run_check_steps
from scripts.checks.docs.db_schema_check import run_db_schema_check
from scripts.checks.docs.doc_header_check import run_doc_header_check
from scripts.checks.docs.doc_naming_check import run_doc_naming_check
from scripts.checks.docs.link_check import run_link_check
from scripts.checks.docs.maps_check import run_maps_check
from scripts.checks.docs.module_ref_check import run_module_ref_check
from scripts.checks.docs.readme_check import run_readme_consistency
from scripts.documentation_ui.check import run_reference_docs_check


def run_docs_check(
    repo_root: Path,
    *,
    enforce: bool = False,
    quiet: bool = False,
    include_reference_docs: bool = True,
) -> int:
    exit_code = run_check_steps(
        [
            CheckStep(
                "README consistency",
                lambda: run_readme_consistency(
                    repo_root=repo_root,
                    enforce_style=enforce,
                    quiet=quiet,
                ),
            ),
            CheckStep("Maps drift", lambda: run_maps_check(repo_root=repo_root, enforce=enforce, quiet=quiet)),
            CheckStep("Doc links", lambda: run_link_check(repo_root=repo_root, enforce=enforce, quiet=quiet)),
            CheckStep(
                "Doc module refs",
                lambda: run_module_ref_check(repo_root=repo_root, enforce=enforce, quiet=quiet),
            ),
            CheckStep(
                "DB schema docs",
                lambda: run_db_schema_check(repo_root=repo_root, enforce=enforce, quiet=quiet),
            ),
            CheckStep(
                "Doc headers",
                lambda: run_doc_header_check(repo_root=repo_root, enforce=enforce, quiet=quiet),
            ),
            CheckStep(
                "Doc naming",
                lambda: run_doc_naming_check(repo_root=repo_root, enforce=enforce, quiet=quiet),
            ),
            CheckStep(
                "Reference docs",
                lambda: run_reference_docs_check(repo_root=repo_root),
                skip=not include_reference_docs,
            ),
        ]
    )
    if exit_code != 0:
        return exit_code

    print("\nDocumentation checks completed successfully.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run documentation and documentation-drift checks together.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit non-zero when enforce-capable checks find problems.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Collapse clean checks to one-line PASS output.",
    )
    parser.add_argument(
        "--skip-reference-docs",
        action="store_true",
        help="Skip generated documentation UI asset checks.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_docs_check(
        repo_root=repo_root,
        enforce=args.enforce,
        quiet=args.quiet,
        include_reference_docs=not args.skip_reference_docs,
    )


if __name__ == "__main__":
    raise SystemExit(main())
