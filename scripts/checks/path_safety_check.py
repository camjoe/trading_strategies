from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from common.paths.formatting import relative_posix
from common.paths.repo_paths import get_repo_root


SOURCE_ROOTS = (
    "scripts",
    "src",
    "apps/paper_trading_web/backend",
    "apps/trends",
)
IGNORED_DIR_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    "coverage",
}

DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:\\")
RELATIVE_BACKSLASH_PATH_RE = re.compile(r"(^|[./])[^'\"\n]*\\[^'\"\n]*\.[A-Za-z0-9]{1,8}($|[?#])")


@dataclass
class FileReport:
    path: Path
    problems: list[str] = field(default_factory=list)


def discover_python_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root_name in SOURCE_ROOTS:
        root = repo_root / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if any(part in IGNORED_DIR_PARTS for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _looks_like_hardcoded_backslash_path(value: str) -> bool:
    return bool(DRIVE_PATH_RE.search(value) or RELATIVE_BACKSLASH_PATH_RE.search(value))


class PathSafetyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.problems: list[str] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if _call_name(node) == "os.sep":
            self.problems.append(f"line {node.lineno}: use pathlib/common path helpers instead of os.sep")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _call_name(node.func) == "os.path.join":
            self.problems.append(f"line {node.lineno}: use pathlib.Path instead of os.path.join")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and _looks_like_hardcoded_backslash_path(node.value):
            self.problems.append(f"line {node.lineno}: hardcoded backslash path string")
        self.generic_visit(node)


def check_file(path: Path) -> FileReport:
    report = FileReport(path=path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except SyntaxError:
        return report

    visitor = PathSafetyVisitor()
    visitor.visit(tree)
    report.problems.extend(visitor.problems)
    return report


def run_path_safety_check(repo_root: Path, *, enforce: bool = False, quiet: bool = False) -> int:
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2

    reports = [report for path in discover_python_files(repo_root) if (report := check_file(path)).problems]
    total = sum(len(report.problems) for report in reports)

    if quiet and not total:
        print("PASS: path safety - no clear cross-platform path hazards found.")
        return 0

    print("Path Safety Check")
    print(f"Repo root: {repo_root}")
    print("Mode: " + ("enforced" if enforce else "advisory"))
    print(f"Problems: {total}")

    if total:
        print("\nFindings:")
        for report in reports:
            rel = relative_posix(report.path, repo_root)
            for problem in report.problems:
                print(f"- {rel}: {problem}")

    if enforce and total:
        print("\nFAIL: path safety check failed in enforce mode.")
        return 1
    if total:
        print("\nWARN: path safety check found problems.")
    else:
        print("\nPASS: no clear cross-platform path hazards found.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check for clear cross-platform path hazards in production/tooling Python modules.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit non-zero when problems are found (default: advisory, always exit 0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_path_safety_check(repo_root=repo_root, enforce=args.enforce)


if __name__ == "__main__":
    raise SystemExit(main())
