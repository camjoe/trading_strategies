from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from common.git import get_repo_root
from common.paths import relative_posix

PYTHON_ROOTS = (
    "scripts",
    "src",
    "apps/paper_trading_web/backend",
    "apps/trends",
)
TEXT_GLOBS = (
    ".github/**/*.yml",
    ".github/**/*.yaml",
    "*.toml",
    "*.ini",
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
SECRET_NAME_RE = re.compile(r"(api[_-]?key|secret|token|password|cookie)", re.IGNORECASE)
TEXT_ASSIGNMENT_RE = re.compile(
    r"(?P<name>[A-Za-z0-9_.-]*(?:api[_-]?key|secret|token|password|cookie)[A-Za-z0-9_.-]*)\s*[:=]\s*(?P<value>.+)",
    re.IGNORECASE,
)
PLACEHOLDER_RE = re.compile(
    r"^(|none|null|false|true|0|1|changeme|change-me|example|dummy|test|placeholder|"
    r"your[-_ ].*|<.*>|\$\{\{.*\}\}|\$\{.*\})$",
    re.IGNORECASE,
)


@dataclass
class FileReport:
    path: Path
    problems: list[str] = field(default_factory=list)


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIR_PARTS for part in path.parts) or path.name == ".env.example"


def discover_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root_name in PYTHON_ROOTS:
        root = repo_root / root_name
        if root.is_dir():
            files.extend(path for path in root.rglob("*.py") if not _is_ignored(path))
    for glob in TEXT_GLOBS:
        files.extend(path for path in repo_root.glob(glob) if path.is_file() and not _is_ignored(path))
    return sorted(set(files))


def _constant_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _target_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _constant_string(node.slice)
    return None


def _looks_like_real_secret(value: str) -> bool:
    normalized = value.strip().strip("\"'")
    return len(normalized) >= 8 and not PLACEHOLDER_RE.match(normalized)


def _is_env_var_name_constant(name: str) -> bool:
    return name.upper().endswith("_ENV")


class SecretVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.problems: list[str] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        value = _constant_string(node.value)
        if value is not None and _looks_like_real_secret(value):
            for target in node.targets:
                name = _target_name(target)
                if name and not _is_env_var_name_constant(name) and SECRET_NAME_RE.search(name):
                    self.problems.append(f"line {node.lineno}: constant assigned to sensitive name `{name}`")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        value = _constant_string(node.value) if node.value is not None else None
        name = _target_name(node.target)
        if (
            name
            and value is not None
            and not _is_env_var_name_constant(name)
            and SECRET_NAME_RE.search(name)
            and _looks_like_real_secret(value)
        ):
            self.problems.append(f"line {node.lineno}: constant assigned to sensitive name `{name}`")
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value_node in zip(node.keys, node.values, strict=False):
            key_value = _constant_string(key) if key is not None else None
            value = _constant_string(value_node)
            if key_value and value and SECRET_NAME_RE.search(key_value) and _looks_like_real_secret(value):
                self.problems.append(f"line {value_node.lineno}: constant mapped to sensitive key `{key_value}`")
        self.generic_visit(node)


def _check_python_file(path: Path) -> FileReport:
    report = FileReport(path=path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except SyntaxError:
        return report
    visitor = SecretVisitor()
    visitor.visit(tree)
    report.problems.extend(visitor.problems)
    return report


def _check_text_file(path: Path) -> FileReport:
    report = FileReport(path=path)
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = TEXT_ASSIGNMENT_RE.search(stripped)
        if match and _looks_like_real_secret(match.group("value").strip()):
            report.problems.append(f"line {line_no}: literal value assigned to sensitive name `{match.group('name')}`")
    return report


def check_file(path: Path) -> FileReport:
    if path.suffix == ".py":
        return _check_python_file(path)
    return _check_text_file(path)


def run_secret_hygiene_check(repo_root: Path, *, enforce: bool = False, quiet: bool = False) -> int:
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2

    reports = [report for path in discover_files(repo_root) if (report := check_file(path)).problems]
    total = sum(len(report.problems) for report in reports)

    if quiet and not total:
        print("PASS: secret hygiene - no committed literal secrets found.")
        return 0

    print("Secret Hygiene Check")
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
        print("\nFAIL: secret hygiene check failed in enforce mode.")
        return 1
    if total:
        print("\nWARN: secret hygiene check found problems.")
    else:
        print("\nPASS: no committed literal secrets found.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check source/config files for committed literal secrets.",
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
    return run_secret_hygiene_check(repo_root=repo_root, enforce=args.enforce)


if __name__ == "__main__":
    raise SystemExit(main())
