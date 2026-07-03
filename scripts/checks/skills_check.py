from __future__ import annotations

import argparse
import re
from pathlib import Path

from common.paths.repo_paths import get_repo_root


# Validates the two mechanical invariants of the skills surface (docs/conventions/
# documentation-maintenance.md, principle 2):
#   1. The AGENTS.md "Current skill inventory" table matches the .ai/skills/ folders on disk,
#      in both directions.
#   2. Every SKILL.md carries complete frontmatter (name / description / invoker) with a valid
#      invoker value.
# Humans author the meaning (purpose text, routing); this check only verifies the mechanical.

SKILLS_DIR = Path(".ai") / "skills"
AGENTS_FILE = "AGENTS.md"

# An inventory row's FIRST cell is the backticked skill folder (routing-table rows have task text
# in the first cell, so they do not match).
INVENTORY_ROW_RE = re.compile(r"^\|\s*`([a-z0-9-]+)/`\s*\|")

REQUIRED_FRONTMATTER = ("name", "description", "invoker")
INVOKER_VOCAB = {"any", "human"}

FRONTMATTER_FIELD_RE = re.compile(r"^([a-z-]+):\s*(.*)$")


def skills_on_disk(repo_root: Path) -> set[str]:
    skills_root = repo_root / SKILLS_DIR
    if not skills_root.is_dir():
        return set()
    return {path.parent.name for path in skills_root.glob("*/SKILL.md")}


def skills_in_inventory(repo_root: Path) -> set[str]:
    agents_md = repo_root / AGENTS_FILE
    if not agents_md.is_file():
        return set()
    found: set[str] = set()
    for line in agents_md.read_text(encoding="utf-8", errors="replace").splitlines():
        match = INVENTORY_ROW_RE.match(line)
        if match:
            found.add(match.group(1))
    return found


def frontmatter_problems(skill_md: Path) -> list[str]:
    lines = skill_md.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or lines[0].strip() != "---":
        return ["missing frontmatter block"]

    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = FRONTMATTER_FIELD_RE.match(line)
        if match:
            fields[match.group(1)] = match.group(2).strip()
    else:
        return ["unterminated frontmatter block"]

    problems = [f"missing frontmatter field: {name}" for name in REQUIRED_FRONTMATTER if not fields.get(name)]
    invoker = fields.get("invoker")
    if invoker and invoker not in INVOKER_VOCAB:
        problems.append(f"invalid invoker: {invoker!r} (allowed: {', '.join(sorted(INVOKER_VOCAB))})")
    return problems


def run_skills_check(repo_root: Path, *, enforce: bool = False, quiet: bool = False) -> int:
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2

    on_disk = skills_on_disk(repo_root)
    in_inventory = skills_in_inventory(repo_root)

    findings: list[str] = []
    for name in sorted(on_disk - in_inventory):
        findings.append(f"- `{SKILLS_DIR.as_posix()}/{name}/` exists but has no {AGENTS_FILE} inventory row")
    for name in sorted(in_inventory - on_disk):
        findings.append(
            f"- {AGENTS_FILE} inventory lists `{name}/` but `{SKILLS_DIR.as_posix()}/{name}/SKILL.md` does not exist"
        )
    for name in sorted(on_disk):
        skill_md = repo_root / SKILLS_DIR / name / "SKILL.md"
        for problem in frontmatter_problems(skill_md):
            findings.append(f"- {SKILLS_DIR.as_posix()}/{name}/SKILL.md: {problem}")

    total = len(findings)

    if quiet and not total:
        print("PASS: skills - inventory and frontmatter in sync.")
        return 0

    print("Skills Drift Check")
    print(f"Repo root: {repo_root}")
    print("Mode: " + ("enforced" if enforce else "advisory"))
    print(f"Skills on disk: {len(on_disk)} | in {AGENTS_FILE} inventory: {len(in_inventory)}")
    print(f"Findings: {total}")

    if total:
        print("\nFindings:")
        for finding in findings:
            print(finding)

    if enforce and total:
        print("\nFAIL: skills drift check failed in enforce mode.")
        return 1
    if total:
        print("\nWARN: skills drift check found problems.")
    else:
        print("\nPASS: skill inventory and frontmatter are in sync.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the AGENTS.md skill inventory matches .ai/skills/ and frontmatter is complete.",
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
    return run_skills_check(repo_root=repo_root, enforce=args.enforce)


if __name__ == "__main__":
    raise SystemExit(main())
