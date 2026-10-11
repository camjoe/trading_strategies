"""Reading a plan from ``plan/``, deciding whether it can be picked up, and marking it claimed."""

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

_TITLE = re.compile(r"^# (?:Plan:\s*)?(.+)$", re.MULTILINE)
_STATUS = re.compile(r"^Status:[ \t]*(.*)$", re.MULTILINE)
_BRANCH = re.compile(r"^Branch to use:\s*`([^`]+)`", re.MULTILINE)
_ROW = re.compile(r"^\|\s*\[(?P<file>[^\]]+)\]\([^)]*\)\s*\|(?P<status>[^|]*)\|(?P<depends>[^|]*)\|\s*$", re.MULTILINE)
_BRANCH_NAME = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._/-]*$")
_WRAP = 100


@dataclass(frozen=True)
class Plan:
    file: str
    title: str
    status: str
    branch: str
    depends_on: str | None


def load_plan(plan_file: Path, readme: Path) -> Plan:
    """The plan in *plan_file*, with its dependencies from the plan index in *readme*."""
    text = plan_file.read_text(encoding="utf-8")
    title = _TITLE.search(text)
    status = _STATUS.search(text)
    branch = _BRANCH.search(text)
    row = next(
        (match for match in _ROW.finditer(readme.read_text(encoding="utf-8")) if match["file"] == plan_file.name), None
    )
    return Plan(
        file=plan_file.name,
        title=title.group(1).strip() if title else plan_file.stem,
        status=status.group(1).strip() if status else "",
        branch=branch.group(1) if branch else f"feature/{plan_file.stem}",
        depends_on=row["depends"].strip() if row else None,
    )


def pickup_problems(plan: Plan, depends_ok: bool = False) -> list[str]:
    """Reasons *plan* must not be picked up; empty when it can be."""
    problems: list[str] = []
    status = plan.status.lower()
    if plan.file.lower() == "readme.md":
        problems.append("The plan index is not a plan.")
    if "in progress" in status:
        problems.append(f"Already in progress: {plan.status}")
    if "blocked" in status:
        problems.append(f"Blocked: {plan.status}")
    if plan.depends_on is None:
        problems.append("The plan is not listed in the plan index, so its dependencies are unknown.")
    elif not plan.depends_on.lower().startswith("none") and not depends_ok:
        problems.append(f"It depends on: {plan.depends_on}. Pass --depends-ok once that is satisfied.")
    if not _BRANCH_NAME.match(plan.branch) or ".." in plan.branch:
        problems.append(f"The branch name is not usable: {plan.branch}")
    return problems


def claimed_status(branch: str, previous: str) -> str:
    return f"in progress (branch `{branch}`). Before pickup: {previous}".rstrip()


def claimed_plan_text(text: str, branch: str) -> str:
    """*text* with its Status line (and any lines continuing it) replaced by a claim."""
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith("Status:")), None)
    if start is None:
        return text
    end = start + 1
    while end < len(lines) and lines[end].strip() and not lines[end].startswith(("Branch to use:", "#")):
        end += 1
    previous = " ".join(part.strip() for part in [lines[start].removeprefix("Status:"), *lines[start + 1 : end]])
    wrapped = textwrap.wrap(f"Status: {claimed_status(branch, previous.strip())}", _WRAP)
    return "\n".join(lines[:start] + wrapped + lines[end:])


def claimed_readme_text(text: str, file: str, branch: str) -> str:
    """*text* with the index row for *file* showing the claim in its Status cell."""

    def replace(match: re.Match[str]) -> str:
        if match["file"] != file:
            return match.group(0)
        status = claimed_status(branch, match["status"].strip())
        link = match.group(0).split("|")[1].strip()
        return f"| {link} | {status} |{match['depends']}|"

    return _ROW.sub(replace, text)


_CLAIM = re.compile(r"^Status:\s*in progress \(branch `([^`]+)`\)", re.IGNORECASE | re.MULTILINE)


def claimed_plan_branch(text: str) -> str | None:
    """The branch a plan was claimed by, from its Status line, or ``None`` if it is not claimed that way."""
    match = _CLAIM.search(text)
    return match.group(1) if match else None


def readme_without_row(text: str, file: str) -> str:
    """*text* with the index row for *file* removed."""
    kept = [line for line in text.split("\n") if not (match := _ROW.match(line)) or match["file"] != file]
    return "\n".join(kept)


def plans_claimed_by(plan_dir: Path, branch: str) -> list[Path]:
    """The plan files in *plan_dir* whose Status says *branch* claimed them."""
    return [
        path
        for path in sorted(plan_dir.glob("*.md"))
        if path.name.lower() != "readme.md" and claimed_plan_branch(path.read_text(encoding="utf-8")) == branch
    ]
