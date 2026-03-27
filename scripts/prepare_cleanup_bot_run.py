#!/usr/bin/env python3
"""Build copy/paste bot-invocation prompts for cleanup agents.

Examples:
    python scripts/prepare_cleanup_bot_run.py --bot python --scope uncommitted
    python scripts/prepare_cleanup_bot_run.py --bot frontend --scope recent --base-ref origin/main
    python scripts/prepare_cleanup_bot_run.py --bot both --scope all --max-files 200
    python scripts/prepare_cleanup_bot_run.py --bot structure --scope recent --base-ref origin/main
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from common.repo_paths import get_repo_root


@dataclass(frozen=True)
class BotSpec:
    name: str
    roots: tuple[str, ...]
    extensions: tuple[str, ...]


BOT_SPECS: dict[str, BotSpec] = {
    "python": BotSpec(
        name="Python Code Cleanup",
        roots=(
            "common",
            "trading",
            "trends",
            "paper_trading_ui/backend",
            "tests",
            "scripts",
        ),
        extensions=(".py", ".md", ".json", ".yml", ".yaml", ".toml", ".ini"),
    ),
    "frontend": BotSpec(
        name="Frontend Code Cleanup",
        roots=("paper_trading_ui/frontend",),
        extensions=(".ts", ".tsx", ".js", ".jsx", ".css", ".scss", ".json", ".md"),
    ),
    "both": BotSpec(
        name="Cross-Stack Cleanup Coordinator",
        roots=(
            "common",
            "trading",
            "trends",
            "paper_trading_ui/backend",
            "paper_trading_ui/frontend",
            "tests",
            "scripts",
        ),
        extensions=(
            ".py",
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".css",
            ".scss",
            ".md",
            ".json",
            ".yml",
            ".yaml",
            ".toml",
            ".ini",
        ),
    ),
    "structure": BotSpec(
        name="Project Structure Steward",
        roots=(
            "common",
            "trading",
            "trends",
            "paper_trading_ui/backend",
            "paper_trading_ui/frontend",
            "tests",
            "scripts",
            "docs",
            ".github/workflows",
            ".github/agents",
        ),
        extensions=(
            ".py",
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".md",
            ".json",
            ".yml",
            ".yaml",
            ".toml",
            ".ini",
        ),
    ),
}

IGNORED_PATH_PARTS = {
    ".git",
    ".venv",
    "tools",
    "node_modules",
    "dist",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
}

IGNORED_FILES = {
    "package-lock.json",
    "package.json",
    "vite-env.d.ts",
    "styles.css",
    "tsconfig.json",
    "vitest.config.ts",
    "eslint.config.js",
    "README.md",
}

IGNORED_PATTERNS = {
    ".test.ts",
    ".test.tsx",
    ".config.js",
    ".config.ts",
    ".example.json",
}

IGNORED_DIRS = {
    "account_profiles",  # JSON data files, not code
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare cleanup-bot invocation prompts.")
    parser.add_argument("--bot", choices=("python", "frontend", "both", "structure"), required=True)
    parser.add_argument(
        "--scope",
        choices=("recent", "uncommitted", "all"),
        required=True,
        help="File selection mode.",
    )
    parser.add_argument(
        "--base-ref",
        default="HEAD~1",
        help="Base ref for --scope recent (default: HEAD~1).",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=150,
        help="Maximum files to include in the prompt list (default: 150).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output instead of text.",
    )
    return parser.parse_args()


def run_git(args: list[str], repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "git command failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def normalize_paths(raw_paths: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in raw_paths:
        # Handle rename output format from some git commands: old -> new
        if " -> " in item:
            item = item.split(" -> ", 1)[1].strip()
        normalized.append(item.replace("\\", "/"))
    return normalized


def collect_recent(repo_root: Path, base_ref: str) -> list[str]:
    return normalize_paths(run_git(["diff", "--name-only", f"{base_ref}...HEAD"], repo_root))


def collect_uncommitted(repo_root: Path) -> list[str]:
    unstaged = run_git(["diff", "--name-only"], repo_root)
    staged = run_git(["diff", "--name-only", "--cached"], repo_root)
    merged = sorted(set(normalize_paths(unstaged + staged)))
    return merged


def _is_ignored(path: Path) -> bool:
    return (
        any(part in IGNORED_PATH_PARTS for part in path.parts)
        or any(part in IGNORED_DIRS for part in path.parts)
        or path.name in IGNORED_FILES
        or any(path.name.endswith(pattern) for pattern in IGNORED_PATTERNS)
    )


def collect_all(repo_root: Path, spec: BotSpec) -> list[str]:
    files: list[str] = []
    for root in spec.roots:
        root_path = repo_root / root
        if not root_path.exists():
            continue
        for path in root_path.rglob("*"):
            if not path.is_file():
                continue
            rel_path = path.relative_to(repo_root)
            if _is_ignored(rel_path):
                continue
            if path.suffix.lower() not in spec.extensions:
                continue
            files.append(rel_path.as_posix())
    return sorted(set(files))


def filter_for_bot(paths: list[str], spec: BotSpec) -> list[str]:
    filtered: list[str] = []
    roots = tuple(f"{root}/" for root in spec.roots)
    for path in paths:
        lower = path.lower()
        rel_path = Path(path)
        if _is_ignored(rel_path):
            continue
        if any(lower.startswith(root.lower()) for root in roots) and rel_path.suffix.lower() in spec.extensions:
            filtered.append(path)
    return sorted(set(filtered))


def format_prompt(agent_name: str, bot_key: str, scope: str, files: list[str], truncated: bool) -> str:
    mode_line = {
        "recent": "changed since base ref",
        "uncommitted": "current staged + unstaged changes",
        "all": "all relevant files for this bot",
    }[scope]
    items = "\n".join(f"- {path}" for path in files) if files else "- (no matching files found)"
    trunc_line = "\nNote: file list was truncated by --max-files." if truncated else ""
    return (
        f"Run the {agent_name} bot.\n"
        f"Selection mode: {mode_line}.\n"
        f"Behavior constraints: preserve existing behavior and public contracts.\n"
        f"Target files:\n{items}{trunc_line}\n\n"
        "After edits, run relevant validation checks and summarize what changed and why."
    )


def main() -> int:
    args = parse_args()
    if args.max_files < 1:
        print("--max-files must be >= 1", file=sys.stderr)
        return 2

    repo_root = get_repo_root(__file__)
    spec = BOT_SPECS[args.bot]

    try:
        if args.scope == "recent":
            selected = collect_recent(repo_root, args.base_ref)
        elif args.scope == "uncommitted":
            selected = collect_uncommitted(repo_root)
        else:
            selected = collect_all(repo_root, spec)
    except RuntimeError as exc:
        print(f"Failed to collect files: {exc}", file=sys.stderr)
        return 1

    files = filter_for_bot(selected, spec)
    truncated = len(files) > args.max_files
    if truncated:
        files = files[: args.max_files]

    prompt_text = format_prompt(spec.name, args.bot, args.scope, files, truncated)
    payload = {
        "bot": args.bot,
        "agent_name": spec.name,
        "scope": args.scope,
        "base_ref": args.base_ref if args.scope == "recent" else None,
        "file_count": len(files),
        "truncated": truncated,
        "files": files,
        "prompt": prompt_text,
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"Agent: {spec.name}")
    print(f"Scope: {args.scope}")
    if args.scope == "recent":
        print(f"Base ref: {args.base_ref}")
    print(f"Files selected: {len(files)}")
    if truncated:
        print("Warning: file list truncated by --max-files")
    print("\nCopy/paste prompt:\n")
    print(prompt_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
