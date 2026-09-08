from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from common.paths.formatting import relative_posix
from common.paths.repo_paths import get_repo_root

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass
class ReadmeReport:
    path: Path
    style_issues: list[str] = field(default_factory=list)


def normalize_rel(path: Path, repo_root: Path) -> str:
    return relative_posix(path, repo_root)


def discover_readmes(repo_root: Path) -> list[Path]:
    ignored_parts = {
        ".git",
        ".venv",
        "venv",
        "local",
        "node_modules",
        "db_backups",
        "__pycache__",
        ".pytest_cache",
    }
    readmes: list[Path] = []

    for candidate in repo_root.rglob("README.md"):
        if any(part in ignored_parts for part in candidate.parts):
            continue
        readmes.append(candidate)

    return sorted(set(readmes))


def extract_headings(content: str) -> list[tuple[int, str]]:
    headings: list[tuple[int, str]] = []
    in_fenced_block = False
    for line in content.splitlines():
        stripped = line.rstrip()
        if stripped.strip().startswith("```"):
            in_fenced_block = not in_fenced_block
            continue
        if in_fenced_block:
            continue

        match = HEADING_RE.match(stripped.strip())
        if match:
            headings.append((len(match.group(1)), match.group(2).strip()))
    return headings


def first_non_empty_line(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def has_any_heading(headings: list[tuple[int, str]], names: set[str]) -> bool:
    lowered = {name.lower() for name in names}
    for _level, heading in headings:
        if heading.lower() in lowered:
            return True
    return False


def evaluate_style(path: Path, repo_root: Path, headings: list[tuple[int, str]], first_line: str) -> list[str]:
    issues: list[str] = []
    rel = normalize_rel(path, repo_root)

    if not first_line.startswith("# "):
        issues.append("First non-empty line should be an H1 heading ('# ...').")

    h1_count = sum(1 for level, _ in headings if level == 1)
    if h1_count != 1:
        issues.append(f"Expected exactly one H1 heading; found {h1_count}.")

    if rel == "README.md":
        recommended_root_sections = {
            "Project Overview",
            "Directory Structure",
            "Quick Start",
            "Testing",
            "Documentation Index",
        }
        missing = [
            section for section in sorted(recommended_root_sections) if not has_any_heading(headings, {section})
        ]
        if missing:
            issues.append("Missing recommended root sections: " + ", ".join(missing))
    else:
        if not has_any_heading(headings, {"Purpose", "Overview"}):
            issues.append("Missing context section: add '## Purpose' or '## Overview'.")
        if not has_any_heading(headings, {"Usage", "Commands", "Workflows", "Workflow", "Quick Start"}):
            issues.append(
                "Missing operational section: add one of '## Usage', '## Commands', "
                "'## Workflows', or '## Quick Start'."
            )

    return issues


def run_readme_consistency(
    repo_root: Path,
    enforce_style: bool = False,
    quiet: bool = False,
) -> int:
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2

    readmes = discover_readmes(repo_root)
    if not readmes:
        print("README Consistency Audit")
        print(f"Repo root: {repo_root}")
        print("No README.md files found.")
        return 0

    reports: list[ReadmeReport] = []
    for path in readmes:
        content = path.read_text(encoding="utf-8", errors="replace")
        headings = extract_headings(content)
        report = ReadmeReport(path=path)
        report.style_issues = evaluate_style(
            path,
            repo_root,
            headings,
            first_non_empty_line(content),
        )
        reports.append(report)

    style_issue_count = sum(len(report.style_issues) for report in reports)

    # Quiet mode: when everything is clean, collapse to a single line. Any issue
    # falls through to the full advisory report below so warnings stay visible.
    if quiet and not style_issue_count:
        print(f"PASS: README consistency - {len(reports)} files scanned, no issues.")
        return 0

    print("README Consistency Audit")
    print(f"Repo root: {repo_root}")
    print(f"README files scanned: {len(reports)}")
    print("Mode: advisory" + (", style-enforced" if enforce_style else ""))
    print(f"Style issues: {style_issue_count}")

    if style_issue_count:
        print("\nFindings:")
        for report in reports:
            rel = normalize_rel(report.path, repo_root)
            if report.style_issues:
                print(f"- {rel}")
                for issue in report.style_issues:
                    print(f"  style: {issue}")

    if enforce_style and style_issue_count > 0:
        print("\nFAIL: README consistency audit failed in enforce mode.")
        return 1

    if style_issue_count:
        print("\nWARN: README consistency audit found advisory issues.")
    else:
        print("\nPASS: README consistency audit passed.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run README consistency audit as a standalone check.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    parser.add_argument(
        "--enforce-style",
        action="store_true",
        help="Exit non-zero when README style issues are found.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)

    exit_code = run_readme_consistency(
        repo_root=repo_root,
        enforce_style=args.enforce_style,
    )
    if exit_code == 0:
        print("\nREADME consistency check completed successfully.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
