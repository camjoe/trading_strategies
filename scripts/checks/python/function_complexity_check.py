from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from scripts.checks.python.public_api_test_evidence_check import changed_files, changed_line_numbers

SOURCE_ROOTS = (
    "scripts",
    "src",
    "apps/paper_trading_web/backend",
    "apps/trends",
)
TEST_ROOT = "tests"
MAX_FUNCTION_LINES = 100
MAX_BRANCHES = 12
MAX_NESTING_DEPTH = 4
MAX_LOCALS = 20


@dataclass(frozen=True)
class FunctionFinding:
    path: str
    qualname: str
    lineno: int
    reasons: tuple[str, ...]


@dataclass
class FunctionComplexityReport:
    changed_functions: int = 0
    findings: list[FunctionFinding] = field(default_factory=list)


def _normalize(path: str) -> str:
    return path.replace("\\", "/")


def _is_source_path(path: str) -> bool:
    normalized = _normalize(path)
    if not normalized.endswith(".py") or normalized.startswith(f"{TEST_ROOT}/"):
        return False
    return any(normalized == root or normalized.startswith(f"{root}/") for root in SOURCE_ROOTS)


def _iter_functions(tree: ast.Module) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    functions: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append((node.name, node))
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append((f"{node.name}.{child.name}", child))
    return functions


def _changed_functions(
    tree: ast.Module,
    changed_lines: set[int],
) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    changed: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for qualname, node in _iter_functions(tree):
        end_lineno = getattr(node, "end_lineno", node.lineno)
        if any(node.lineno <= line <= end_lineno for line in changed_lines):
            changed.append((qualname, node))
    return changed


def analyze_function(qualname: str, node: ast.FunctionDef | ast.AsyncFunctionDef, path: str) -> FunctionFinding | None:
    line_count = getattr(node, "end_lineno", node.lineno) - node.lineno + 1
    branch_count = _branch_count(node)
    nesting_depth = _max_nesting_depth(node)
    local_count = _local_count(node)

    reasons: list[str] = []
    if line_count > MAX_FUNCTION_LINES:
        reasons.append(f"{line_count} lines")
    if branch_count > MAX_BRANCHES:
        reasons.append(f"{branch_count} branches")
    if nesting_depth > MAX_NESTING_DEPTH:
        reasons.append(f"nesting depth {nesting_depth}")
    if local_count > MAX_LOCALS:
        reasons.append(f"{local_count} local names")

    if not reasons:
        return None
    return FunctionFinding(path=path, qualname=qualname, lineno=node.lineno, reasons=tuple(reasons))


def _branch_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    branch_nodes = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.ExceptHandler,
        ast.With,
        ast.AsyncWith,
        ast.BoolOp,
        ast.IfExp,
        ast.Match,
    )
    return sum(isinstance(child, branch_nodes) for child in ast.walk(node))


def _max_nesting_depth(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    nesting_nodes = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.With,
        ast.AsyncWith,
        ast.Match,
    )

    def visit(current: ast.AST, depth: int) -> int:
        next_depth = depth + 1 if isinstance(current, nesting_nodes) else depth
        child_depths = [visit(child, next_depth) for child in ast.iter_child_nodes(current)]
        return max([next_depth, *child_depths])

    return visit(node, 0)


def _local_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    names = {arg.arg for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]}
    if node.args.vararg:
        names.add(node.args.vararg.arg)
    if node.args.kwarg:
        names.add(node.args.kwarg.arg)

    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            names.add(child.id)
        if isinstance(child, ast.ExceptHandler) and child.name:
            names.add(child.name)
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and child is not node:
            names.add(child.name)
    return len(names)


def check_file(repo_root: Path, path: str, changed_lines: set[int]) -> FunctionComplexityReport:
    report = FunctionComplexityReport()
    absolute = repo_root / path
    if not absolute.is_file():
        return report

    try:
        tree = ast.parse(absolute.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return report

    for qualname, node in _changed_functions(tree, changed_lines):
        report.changed_functions += 1
        finding = analyze_function(qualname, node, path)
        if finding:
            report.findings.append(finding)
    return report


def build_report(repo_root: Path, *, base_ref: str | None = None) -> FunctionComplexityReport:
    report = FunctionComplexityReport()
    for path in sorted(path for path in changed_files(repo_root, base_ref=base_ref) if _is_source_path(path)):
        file_report = check_file(repo_root, path, changed_line_numbers(repo_root, path, base_ref=base_ref))
        report.changed_functions += file_report.changed_functions
        report.findings.extend(file_report.findings)
    return report


def run_function_complexity_check(repo_root: Path, *, base_ref: str | None = None, quiet: bool = False) -> int:
    report = build_report(repo_root, base_ref=base_ref)

    if quiet and not report.findings:
        print("PASS: Function complexity - no changed functions exceed advisory thresholds.")
        return 0

    print("Function Complexity Check")
    print(f"Repo root: {repo_root}")
    print(f"Diff: {base_ref + '...HEAD' if base_ref else 'HEAD'}")
    print(f"Changed functions inspected: {report.changed_functions}")

    if report.findings:
        print("\nAdvisory findings:")
        for finding in report.findings:
            reasons = ", ".join(finding.reasons)
            print(f"- {finding.path}:{finding.lineno}: {finding.qualname} exceeds advisory thresholds ({reasons})")
        print("\nWARN: Review these functions for possible split points or simpler control flow.")
    else:
        print("\nPASS: No changed functions exceed advisory thresholds.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Advisory check for changed Python functions with high size or complexity signals.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--base", metavar="REF", default=None, help="Inspect changes vs a git ref.")
    parser.add_argument("--quiet", action="store_true", help="Collapse clean output to one PASS line.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_function_complexity_check(repo_root=repo_root, base_ref=args.base, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
