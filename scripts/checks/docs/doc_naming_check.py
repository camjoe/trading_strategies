from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from common.paths.formatting import relative_posix
from common.paths.repo_paths import get_repo_root

# Mechanical filename rules from docs/conventions/naming.md. Humans still choose the title and
# scope; this checker verifies that doc paths stay predictable.

RESERVED_NAMES = {
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "SKILL.md",
}

KEBAB_MD_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
TEMPLATE_RE = re.compile(r"^TEMPLATE\.[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
ADR_RE = re.compile(r"^(\d{3})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")


@dataclass
class NamingReport:
    path: Path
    problems: list[str] = field(default_factory=list)


def discover_docs(repo_root: Path) -> list[Path]:
    docs_dir = repo_root / "docs"
    if not docs_dir.is_dir():
        return []
    return sorted(docs_dir.rglob("*.md"))


def check_file(path: Path, repo_root: Path) -> NamingReport:
    report = NamingReport(path=path)
    name = path.name
    rel_parts = path.relative_to(repo_root).parts
    in_adr = len(rel_parts) >= 2 and rel_parts[0] == "docs" and rel_parts[1] == "adr"

    if name in RESERVED_NAMES or TEMPLATE_RE.match(name):
        return report

    if in_adr:
        if not ADR_RE.match(name):
            report.problems.append("ADR filename must be `NNN-kebab-case.md`")
        return report

    if not KEBAB_MD_RE.match(name):
        report.problems.append("docs filename must be lowercase kebab-case `.md`")
    return report


def _adr_numbers(paths: list[Path], repo_root: Path) -> list[tuple[Path, int]]:
    numbered: list[tuple[Path, int]] = []
    for path in paths:
        rel_parts = path.relative_to(repo_root).parts
        if len(rel_parts) < 2 or rel_parts[0] != "docs" or rel_parts[1] != "adr":
            continue
        match = ADR_RE.match(path.name)
        if match:
            numbered.append((path, int(match.group(1))))
    return numbered


def _adr_number_problems(paths: list[Path], repo_root: Path) -> list[str]:
    numbered = _adr_numbers(paths, repo_root)
    by_number: dict[int, list[Path]] = {}
    for path, number in numbered:
        by_number.setdefault(number, []).append(path)

    findings: list[str] = []
    for number, duplicates in sorted(by_number.items()):
        if len(duplicates) > 1:
            names = ", ".join(relative_posix(path, repo_root) for path in duplicates)
            findings.append(f"duplicate ADR number {number:03}: {names}")
    return findings


def run_doc_naming_check(repo_root: Path, *, enforce: bool = False, quiet: bool = False) -> int:
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2

    docs = discover_docs(repo_root)
    reports = [report for path in docs if (report := check_file(path, repo_root)).problems]
    number_findings = _adr_number_problems(docs, repo_root)
    total = sum(len(report.problems) for report in reports) + len(number_findings)

    if quiet and not total:
        print("PASS: doc names - filenames and ADR numbering follow convention.")
        return 0

    print("Doc Naming Check")
    print(f"Repo root: {repo_root}")
    print("Mode: " + ("enforced" if enforce else "advisory"))
    print(f"Naming problems: {total}")

    if total:
        print("\nFindings:")
        for report in reports:
            rel = relative_posix(report.path, repo_root)
            for problem in report.problems:
                print(f"- {rel}: {problem}")
        for problem in number_findings:
            print(f"- docs/adr/: {problem}")

    if enforce and total:
        print("\nFAIL: doc naming check failed in enforce mode.")
        return 1
    if total:
        print("\nWARN: doc naming check found problems.")
    else:
        print("\nPASS: doc filenames and ADR numbering follow convention.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify docs/ filenames follow kebab-case and ADRs use unique NNN prefixes.",
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
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_doc_naming_check(repo_root=repo_root, enforce=args.enforce)


if __name__ == "__main__":
    raise SystemExit(main())
