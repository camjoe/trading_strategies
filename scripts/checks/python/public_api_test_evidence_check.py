from __future__ import annotations

import argparse
import ast
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from common.paths.repo_paths import get_repo_root

SOURCE_ROOTS = (
    "scripts",
    "src",
    "apps/paper_trading_web/backend",
    "apps/trends",
)
TEST_ROOT = "tests"
HUNK_RE = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class ChangedFunction:
    path: str
    qualname: str
    lineno: int


@dataclass
class ApiTestEvidenceReport:
    changed_functions: list[ChangedFunction] = field(default_factory=list)
    changed_tests: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _normalize(path: str) -> str:
    return path.replace("\\", "/")


def _is_source_path(path: str) -> bool:
    normalized = _normalize(path)
    if not normalized.endswith(".py") or normalized.startswith(f"{TEST_ROOT}/"):
        return False
    return any(normalized == root or normalized.startswith(f"{root}/") for root in SOURCE_ROOTS)


def _is_test_path(path: str) -> bool:
    normalized = _normalize(path)
    return normalized.startswith(f"{TEST_ROOT}/") and normalized.endswith(".py")


def changed_files(repo_root: Path, base_ref: str | None = None) -> list[str]:
    if base_ref:
        command = ["git", "diff", "--name-only", f"{base_ref}...HEAD"]
    else:
        command = ["git", "diff", "--name-only", "HEAD"]
    diff_completed = subprocess.run(command, cwd=repo_root, check=True, capture_output=True, text=True)
    untracked_completed = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = {
        _normalize(line.strip())
        for output in (diff_completed.stdout, untracked_completed.stdout)
        for line in output.splitlines()
        if line.strip()
    }
    return sorted(paths)


def changed_line_numbers(repo_root: Path, path: str, base_ref: str | None = None) -> set[int]:
    absolute = repo_root / path
    if not _is_tracked(repo_root, path) and absolute.is_file():
        return set(range(1, len(absolute.read_text(encoding="utf-8", errors="replace").splitlines()) + 1))

    if base_ref:
        command = ["git", "diff", "--unified=0", f"{base_ref}...HEAD", "--", path]
    else:
        command = ["git", "diff", "--unified=0", "HEAD", "--", path]
    completed = subprocess.run(command, cwd=repo_root, check=True, capture_output=True, text=True)

    lines: set[int] = set()
    for diff_line in completed.stdout.splitlines():
        match = HUNK_RE.search(diff_line)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count == 0:
            continue
        lines.update(range(start, start + count))
    return lines


def _is_tracked(repo_root: Path, path: str) -> bool:
    completed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _public_functions(tree: ast.Module) -> list[ChangedFunction]:
    functions: list[ChangedFunction] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            functions.append(ChangedFunction("", node.name, node.lineno))
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and not child.name.startswith("_"):
                    functions.append(ChangedFunction("", f"{node.name}.{child.name}", child.lineno))

    return functions


def changed_public_functions(repo_root: Path, path: str, changed_lines: set[int]) -> list[ChangedFunction]:
    absolute = repo_root / path
    if not absolute.is_file():
        return []

    try:
        tree = ast.parse(absolute.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []

    changed: list[ChangedFunction] = []
    for function in _public_functions(tree):
        node = _node_by_qualname(tree, function.qualname)
        if node is None:
            continue
        end_lineno = getattr(node, "end_lineno", node.lineno)
        if any(node.lineno <= line <= end_lineno for line in changed_lines):
            changed.append(ChangedFunction(path, function.qualname, function.lineno))
    return changed


def _node_by_qualname(tree: ast.Module, qualname: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    parts = qualname.split(".")
    if len(parts) == 1:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == parts[0]:
                return node
        return None

    class_name, function_name = parts
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == function_name:
                    return child
    return None


def has_nearby_test_change(source_path: str, changed_tests: list[str]) -> bool:
    if not changed_tests:
        return False

    normalized = _normalize(source_path)
    source = Path(normalized)
    stem = source.stem
    candidates = _candidate_test_paths(normalized)

    for test_path in changed_tests:
        test = _normalize(test_path)
        test_name = Path(test).name
        if test in candidates:
            return True
        if test_name in {f"test_{stem}.py", f"{stem}_test.py"}:
            return True
    return False


def _candidate_test_paths(source_path: str) -> set[str]:
    source = Path(source_path)
    candidates = {
        f"{TEST_ROOT}/{source.parent.as_posix()}/test_{source.stem}.py",
        f"{TEST_ROOT}/{source.parent.as_posix()}/{source.stem}_test.py",
    }

    parts = source.parts
    if parts and parts[0] == "src" and len(parts) > 1:
        stripped = Path(*parts[1:])
        candidates.add(f"{TEST_ROOT}/{stripped.parent.as_posix()}/test_{stripped.stem}.py")
    if parts and parts[0] == "scripts":
        candidates.add(f"{TEST_ROOT}/scripts/test_{source.stem}.py")
    if len(parts) >= 3 and parts[0] == "apps":
        candidates.add(f"{TEST_ROOT}/{source.parent.as_posix()}/test_{source.stem}.py")

    return {_normalize(candidate) for candidate in candidates}


def build_report(repo_root: Path, *, base_ref: str | None = None) -> ApiTestEvidenceReport:
    files = changed_files(repo_root, base_ref=base_ref)
    changed_tests = sorted(path for path in files if _is_test_path(path))
    report = ApiTestEvidenceReport(changed_tests=changed_tests)

    for path in sorted(path for path in files if _is_source_path(path)):
        functions = changed_public_functions(repo_root, path, changed_line_numbers(repo_root, path, base_ref=base_ref))
        report.changed_functions.extend(functions)
        if functions and not has_nearby_test_change(path, changed_tests):
            names = ", ".join(function.qualname for function in functions)
            report.warnings.append(f"{path}: public API changed without nearby test change ({names})")

    return report


def run_public_api_test_evidence_check(repo_root: Path, *, base_ref: str | None = None, quiet: bool = False) -> int:
    try:
        report = build_report(repo_root, base_ref=base_ref)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: failed to inspect git diff: {' '.join(exc.cmd)}")
        return exc.returncode

    if quiet and not report.warnings:
        print("PASS: Public API test evidence - no untested public API changes detected.")
        return 0

    print("Public API Test Evidence Check")
    print(f"Repo root: {repo_root}")
    print(f"Diff: {base_ref + '...HEAD' if base_ref else 'HEAD'}")
    print(f"Changed public functions: {len(report.changed_functions)}")
    print(f"Changed test files: {len(report.changed_tests)}")

    if report.warnings:
        print("\nAdvisory findings:")
        for warning in report.warnings:
            print(f"- {warning}")
        print("\nWARN: Public API changes may need explicit test evidence.")
    else:
        print("\nPASS: Public API changes have nearby test-change evidence or no public API changes were detected.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Advisory check for changed public Python APIs without nearby test changes.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--base", metavar="REF", default=None, help="Inspect changes vs a git ref.")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Collapse clean output to one PASS line.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_public_api_test_evidence_check(repo_root=repo_root, base_ref=args.base, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
