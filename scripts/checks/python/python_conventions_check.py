from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
from pathlib import Path

from common.git import get_repo_root
from common.paths import relative_posix

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
            if path.name == "__init__.py":
                continue
            if any(part in IGNORED_DIR_PARTS for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _has_future_annotations(tree: ast.Module) -> bool:
    body = tree.body
    index = 0
    if body and isinstance(body[0], ast.Expr):
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            index = 1
    if index >= len(body):
        return False
    node = body[index]
    return (
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
    )


def _is_public_function(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")


def check_file(path: Path) -> FileReport:
    report = FileReport(path=path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except SyntaxError:
        return report

    if not _has_future_annotations(tree):
        report.problems.append("missing `from __future__ import annotations`")

    for node in ast.walk(tree):
        if _is_public_function(node) and node.returns is None:
            report.problems.append(f"public function `{node.name}` missing return annotation at line {node.lineno}")

    return report


def run_python_conventions_check(repo_root: Path, *, enforce: bool = False, quiet: bool = False) -> int:
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2

    reports = [report for path in discover_python_files(repo_root) if (report := check_file(path)).problems]
    total = sum(len(report.problems) for report in reports)

    if quiet and not total:
        print("PASS: Python conventions - future annotations and public return types are present.")
        return 0

    print("Python Conventions Check")
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
        print("\nFAIL: Python conventions check failed in enforce mode.")
        return 1
    if total:
        print("\nWARN: Python conventions check found problems.")
    else:
        print("\nPASS: Python conventions are satisfied.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check production/tooling Python modules for future annotations and public return types.",
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
    return run_python_conventions_check(repo_root=repo_root, enforce=args.enforce)


if __name__ == "__main__":
    raise SystemExit(main())
