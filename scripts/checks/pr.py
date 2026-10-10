from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from common.git import changed_paths, get_repo_root, resolve_ref, uncommitted_paths
from scripts.checks._runner import CheckStep, resolve_python_exe, run_check_steps
from scripts.checks.docs.docs_check import run_docs_check
from scripts.checks.quick import run_quick

DEFAULT_BASE_REF = "develop"

# The paths CI's `frontend_related` filter watches (.github/workflows/ci.yml).
FRONTEND_PATHS = ("apps/paper_trading_web/frontend/", ".github/workflows/ci.yml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the checks CI enforces on a pull request, targeted at the branch diff.",
    )
    parser.add_argument("--base", metavar="REF", dest="base_ref", default=DEFAULT_BASE_REF, help="Branch base ref.")
    parser.add_argument("--no-cov", action="store_true", help="Disable coverage for faster test runs.")
    return parser.parse_args()


def touches_frontend(paths: list[str]) -> bool:
    return any(path.replace("\\", "/").startswith(FRONTEND_PATHS) for path in paths)


def run_pr(
    repo_root: Path,
    python_exe: str,
    base_ref: str = DEFAULT_BASE_REF,
    no_cov: bool = False,
) -> int:
    """Run enforced docs checks, repo checks, and branch-targeted Python checks.

    Frontend lint, typecheck, and tests run only when the branch diff touches the frontend.
    Targeting reads the committed diff ``base...HEAD``; uncommitted edits are not seen.
    """
    try:
        with_frontend = touches_frontend(changed_paths(repo_root, base_ref=base_ref))
        base_sha = resolve_ref(repo_root, base_ref)
        uncommitted = uncommitted_paths(repo_root)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: failed to inspect git diff: {' '.join(exc.cmd)}")
        return exc.returncode

    print(f"Targeting {base_ref}...HEAD (base {base_sha})")
    if uncommitted:
        print(
            f"WARNING: {len(uncommitted)} uncommitted file(s). Suite targeting and frontend detection read "
            f"{base_ref}...HEAD, so edits in them may skip checks: {', '.join(uncommitted[:5])}"
            + (" ..." if len(uncommitted) > 5 else "")
        )

    try:
        exit_code = run_check_steps(
            [
                CheckStep(
                    "Documentation checks",
                    lambda: run_docs_check(repo_root=repo_root, enforce=True, quiet=True),
                ),
                CheckStep(
                    "Quick checks",
                    lambda: run_quick(
                        repo_root=repo_root,
                        python_exe=python_exe,
                        with_frontend=with_frontend,
                        suite_base=base_ref,
                        no_cov=no_cov,
                    ),
                ),
            ]
        )
    except subprocess.CalledProcessError as exc:
        print(f"\nStep failed with exit code {exc.returncode}: {' '.join(exc.cmd)}")
        return exc.returncode
    if exit_code != 0:
        return exit_code

    print("\nPR checks completed successfully.")
    return 0


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root(__file__)
    return run_pr(
        repo_root=repo_root,
        python_exe=resolve_python_exe(repo_root),
        base_ref=args.base_ref,
        no_cov=args.no_cov,
    )


if __name__ == "__main__":
    raise SystemExit(main())
