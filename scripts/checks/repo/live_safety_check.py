from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

from common.paths.formatting import relative_posix
from common.paths.repo_paths import get_repo_root


# Mechanical safety check for the live-trading guard documented in
# docs/architecture/architecture-conventions.md. This intentionally enforces only the
# high-confidence rule: automation must not set live_trading_enabled to true/1. The human-only
# broker endpoint review remains a code-review concern because "live endpoint" intent is contextual.

SCAN_GLOBS = (
    "scripts/**/*.py",
    "src/infrastructure/database/**/*.py",
    "src/trading/interfaces/runtime/data_ops/**/*.py",
    "apps/paper_trading_web/backend/**/*.py",
    "tests/support/**/*.py",
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
EXCLUDED_REL_PATHS = {
    "tests/scripts/test_live_safety_check.py",
}

LIVE_FIELD = "live_trading_enabled"


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    message: str


def discover_python_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for glob in SCAN_GLOBS:
        for path in repo_root.glob(glob):
            if not path.is_file():
                continue
            if any(part in IGNORED_DIR_PARTS for part in path.parts):
                continue
            if path.relative_to(repo_root).as_posix() in EXCLUDED_REL_PATHS:
                continue
            files.append(path)
    return sorted(set(files))


def _is_trueish(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value in (1, True)


def _target_names_live_field(target: ast.AST) -> bool:
    if isinstance(target, ast.Name):
        return target.id == LIVE_FIELD
    if isinstance(target, ast.Attribute):
        return target.attr == LIVE_FIELD
    if isinstance(target, ast.Subscript):
        slice_node = target.slice
        return isinstance(slice_node, ast.Constant) and slice_node.value == LIVE_FIELD
    if isinstance(target, (ast.Tuple, ast.List)):
        return any(_target_names_live_field(element) for element in target.elts)
    return False


def _constant_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _string_enables_live_trading(value: str) -> bool:
    normalized = " ".join(value.lower().replace("\n", " ").split())
    return (
        f"{LIVE_FIELD} = 1" in normalized
        or f"{LIVE_FIELD}=1" in normalized
        or f"{LIVE_FIELD} = true" in normalized
        or f"{LIVE_FIELD}=true" in normalized
    )


def _docstring_line_numbers(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if not isinstance(first, ast.Expr):
            continue
        if not isinstance(first.value, ast.Constant) or not isinstance(first.value.value, str):
            continue
        start = getattr(first, "lineno", None)
        end = getattr(first, "end_lineno", start)
        if start is not None and end is not None:
            lines.update(range(start, end + 1))
    return lines


class LiveSafetyVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, docstring_lines: set[int]) -> None:
        self.path = path
        self.docstring_lines = docstring_lines
        self.findings: list[Finding] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        if _is_trueish(node.value) and any(_target_names_live_field(target) for target in node.targets):
            self.findings.append(Finding(self.path, node.lineno, f"sets {LIVE_FIELD} to true/1"))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and _is_trueish(node.value) and _target_names_live_field(node.target):
            self.findings.append(Finding(self.path, node.lineno, f"sets {LIVE_FIELD} to true/1"))
        self.generic_visit(node)

    def visit_keyword(self, node: ast.keyword) -> None:
        if node.arg == LIVE_FIELD and _is_trueish(node.value):
            self.findings.append(Finding(self.path, node.value.lineno, f"passes {LIVE_FIELD}=true/1"))
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values, strict=False):
            if _constant_string(key) == LIVE_FIELD and _is_trueish(value):
                self.findings.append(Finding(self.path, value.lineno, f"maps {LIVE_FIELD} to true/1"))
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if node.lineno not in self.docstring_lines and isinstance(node.value, str):
            if _string_enables_live_trading(node.value):
                self.findings.append(Finding(self.path, node.lineno, f"string literal enables {LIVE_FIELD}"))
        self.generic_visit(node)


def check_file(path: Path) -> list[Finding]:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except SyntaxError:
        return []

    visitor = LiveSafetyVisitor(path=path, docstring_lines=_docstring_line_numbers(tree))
    visitor.visit(tree)
    return visitor.findings


def run_live_safety_check(repo_root: Path, *, enforce: bool = False, quiet: bool = False) -> int:
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2

    findings = [finding for path in discover_python_files(repo_root) for finding in check_file(path)]

    if quiet and not findings:
        print("PASS: live safety - no automated live-trading enablement found.")
        return 0

    print("Live Trading Safety Check")
    print(f"Repo root: {repo_root}")
    print("Mode: " + ("enforced" if enforce else "advisory"))
    print(f"Findings: {len(findings)}")

    if findings:
        print("\nFindings:")
        for finding in findings:
            rel = relative_posix(finding.path, repo_root)
            print(f"- {rel}:{finding.line}: {finding.message}")

    if enforce and findings:
        print("\nFAIL: live trading safety check failed in enforce mode.")
        return 1
    if findings:
        print("\nWARN: live trading safety check found potential automated enablement.")
    else:
        print("\nPASS: no automated live-trading enablement found.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check code does not set live_trading_enabled to true/1.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit non-zero when findings are found (default: advisory, always exit 0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_live_safety_check(repo_root=repo_root, enforce=args.enforce)


if __name__ == "__main__":
    raise SystemExit(main())
