"""Prevent private operator state from being recorded in tracked runbooks."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from common.paths.formatting import relative_posix
from common.paths.repo_paths import get_repo_root


COMPLETED_CHECKBOX_RE = re.compile(r"^\s*- \[[xX]\]", re.MULTILINE)
DATED_VERIFICATION_RE = re.compile(r"\bverified \d{4}-\d{2}-\d{2}\b", re.IGNORECASE)
HOST_STATE_PHRASES = (
    "already applied on this host",
    "this machine runs jobs",
)


@dataclass
class RunbookStateReport:
    """Operator-state findings for one tracked runbook."""

    path: Path
    problems: list[str] = field(default_factory=list)


def discover_runbooks(repo_root: Path) -> list[Path]:
    """Return tracked Markdown runbooks in deterministic order."""
    runbooks_dir = repo_root / "docs" / "runbooks"
    if not runbooks_dir.is_dir():
        return []
    return sorted(runbooks_dir.rglob("*.md"))


def check_file(path: Path) -> RunbookStateReport:
    """Return private operator-state markers found in one runbook."""
    report = RunbookStateReport(path=path)
    text = path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()

    if COMPLETED_CHECKBOX_RE.search(text):
        report.problems.append("completed checklist item; record installation progress under local/operations/")
    if DATED_VERIFICATION_RE.search(text):
        report.problems.append("dated machine verification; record it under local/operations/")
    for phrase in HOST_STATE_PHRASES:
        if phrase in lowered:
            report.problems.append(f"machine-specific state phrase: {phrase!r}")
    return report


def run_runbook_state_check(repo_root: Path, *, enforce: bool = False, quiet: bool = False) -> int:
    """Check tracked runbooks for private operator-state markers."""
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2

    reports = [report for path in discover_runbooks(repo_root) if (report := check_file(path)).problems]
    total = sum(len(report.problems) for report in reports)

    if quiet and not total:
        print("PASS: runbook state - tracked runbooks contain reusable procedures only.")
        return 0

    print("Runbook State Check")
    print(f"Repo root: {repo_root}")
    print("Mode: " + ("enforced" if enforce else "advisory"))
    print(f"Operator-state problems: {total}")

    if total:
        print("\nFindings:")
        for report in reports:
            rel = relative_posix(report.path, repo_root)
            for problem in report.problems:
                print(f"- {rel}: {problem}")

    if enforce and total:
        print("\nFAIL: runbook state check failed in enforce mode.")
        return 1
    if total:
        print("\nWARN: runbook state check found private operator-state markers.")
    else:
        print("\nPASS: tracked runbooks contain reusable procedures only.")
    return 0


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Prevent installation-specific operator state from entering tracked runbooks.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit non-zero when problems are found (default: advisory, always exit 0).",
    )
    return parser.parse_args()


def main() -> int:
    """Run the command-line check."""
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_runbook_state_check(repo_root=repo_root, enforce=args.enforce)


if __name__ == "__main__":
    raise SystemExit(main())
