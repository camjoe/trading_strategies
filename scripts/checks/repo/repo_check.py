from __future__ import annotations

import argparse
from pathlib import Path

from common.git import get_repo_root
from scripts.checks._runner import CheckStep, run_check_steps
from scripts.checks.repo.layer_check import run_layer_check
from scripts.checks.repo.live_safety_check import run_live_safety_check
from scripts.checks.repo.migration_check import run_migration_check
from scripts.checks.repo.path_safety_check import run_path_safety_check
from scripts.checks.repo.review_scope_check import run_review_scope_check
from scripts.checks.repo.secret_hygiene_check import run_secret_hygiene_check
from scripts.checks.repo.sector_map_check import run_sector_map_check
from scripts.checks.repo.skills_check import run_skills_check


def run_repo_check(repo_root: Path, *, enforce: bool = True, quiet: bool = True) -> int:
    """Run repository-level safety and structure checks."""
    exit_code = run_check_steps(
        [
            CheckStep("Layer boundaries", lambda: run_layer_check(repo_root=repo_root)),
            CheckStep(
                "Skills drift",
                lambda: run_skills_check(repo_root=repo_root, quiet=quiet, enforce=enforce),
            ),
            CheckStep(
                "Live-trading safety",
                lambda: run_live_safety_check(repo_root=repo_root, quiet=quiet, enforce=enforce),
            ),
            CheckStep(
                "Migration chain",
                lambda: run_migration_check(repo_root=repo_root, quiet=quiet, enforce=enforce),
            ),
            CheckStep(
                "Path safety",
                lambda: run_path_safety_check(repo_root=repo_root, quiet=quiet, enforce=enforce),
            ),
            CheckStep(
                "Secret hygiene",
                lambda: run_secret_hygiene_check(repo_root=repo_root, quiet=quiet, enforce=enforce),
            ),
            CheckStep(
                "Sector map coverage",
                lambda: run_sector_map_check(repo_root=repo_root, quiet=quiet),
            ),
            CheckStep(
                "Review scope",
                lambda: run_review_scope_check(repo_root=repo_root, quiet=quiet),
            ),
        ]
    )
    if exit_code != 0:
        return exit_code

    print("\nRepository checks completed successfully.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run repository-level safety and structure checks.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument(
        "--advisory",
        action="store_true",
        help="Report findings without failing enforce-capable checks.",
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
    return run_repo_check(repo_root=repo_root, enforce=not args.advisory, quiet=not args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
