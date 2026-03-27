from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_STALE_DOCS = 1
EXIT_INPUT_ERROR = 2
EXIT_GIT_ERROR = 3


def run_git(repo_root: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown git error"
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def normalize_path(value: str) -> str:
    return str(value or "").replace("\\", "/").strip().strip("/").lower()


def top_level_area(path_value: str) -> str:
    normalized = normalize_path(path_value)
    if not normalized:
        return "."
    parts = normalized.split("/")
    if len(parts) == 1:
        return "."
    return parts[0]


def parse_name_status(raw_output: str) -> list[str]:
    paths: list[str] = []
    for line in raw_output.splitlines():
        if not line.strip():
            continue
        columns = line.split("\t")
        path_value = columns[-1].strip() if len(columns) > 1 else ""
        if path_value:
            paths.append(path_value)
    return paths


def load_docs_config(repo_root: Path) -> dict[str, Any]:
    config_candidates = [
        repo_root / ".commit-context-docs.json",
        repo_root / "tools" / ".commit-context-docs.json",
    ]
    config_path = next((candidate for candidate in config_candidates if candidate.exists()), None)
    default_dirs = ["docs"]

    if config_path is None:
        return {
            "configPath": "",
            "documentationDirectories": default_dirs,
            "configError": "",
        }

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "configPath": str(config_path),
            "documentationDirectories": default_dirs,
            "configError": "Could not parse .commit-context-docs.json; using defaults.",
        }

    configured_dirs = payload.get("documentationDirectories")
    raw_directories = configured_dirs if isinstance(configured_dirs, list) else default_dirs
    directories = [normalized for entry in raw_directories if (normalized := normalize_path(str(entry)))]

    return {
        "configPath": str(config_path),
        "documentationDirectories": sorted(set(directories)),
        "configError": "",
    }


def is_documentation_path(path_value: str, docs_config: dict[str, Any]) -> bool:
    normalized = normalize_path(path_value)
    if not normalized:
        return False
    if normalized.endswith("/readme.md") or normalized == "readme.md":
        return True
    for directory in docs_config.get("documentationDirectories") or []:
        if normalized == directory or normalized.startswith(directory + "/"):
            return True
    return False


def collect_working_tree_changes(repo_root: Path) -> list[str]:
    tracked = parse_name_status(run_git(repo_root, "diff", "--name-status", "HEAD"))
    untracked = [
        line.strip()
        for line in run_git(repo_root, "ls-files", "--others", "--exclude-standard").splitlines()
        if line.strip()
    ]
    return sorted(set(tracked + untracked))


def collect_ref_diff_changes(repo_root: Path, base_ref: str, head_ref: str) -> list[str]:
    run_git(repo_root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    run_git(repo_root, "rev-parse", "--verify", f"{head_ref}^{{commit}}")
    diff = run_git(repo_root, "diff", "--name-status", f"{base_ref}...{head_ref}")
    return sorted(set(parse_name_status(diff)))


def evaluate_docs_freshness(changed_paths: list[str], docs_config: dict[str, Any]) -> dict[str, Any]:
    doc_paths = [path for path in changed_paths if is_documentation_path(path, docs_config)]
    non_doc_paths = [path for path in changed_paths if not is_documentation_path(path, docs_config)]

    doc_areas = {top_level_area(path) for path in doc_paths}
    non_doc_areas = {top_level_area(path) for path in non_doc_paths}
    missing_doc_areas = sorted(non_doc_areas - doc_areas)

    needs_review = bool(non_doc_paths and missing_doc_areas)

    return {
        "changedPaths": sorted(set(changed_paths)),
        "documentationChanges": sorted(set(doc_paths)),
        "nonDocumentationChanges": sorted(set(non_doc_paths)),
        "documentationAreas": sorted(doc_areas),
        "nonDocumentationAreas": sorted(non_doc_areas),
        "missingDocumentationAreas": missing_doc_areas,
        "needsDocumentationReview": needs_review,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check documentation freshness for changed areas and fail when code changes "
            "are missing matching docs updates."
        )
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root to inspect. Defaults to current working directory.",
    )
    parser.add_argument(
        "--base-ref",
        help=(
            "Git base ref for CI-style comparison. When set, changes are read from "
            "git diff <base-ref>...<head-ref>."
        ),
    )
    parser.add_argument(
        "--head-ref",
        default="HEAD",
        help="Git head ref for CI-style comparison. Default: HEAD.",
    )
    parser.add_argument(
        "--strict-config",
        action="store_true",
        help="Fail when .commit-context-docs.json exists but cannot be parsed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()

    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return EXIT_INPUT_ERROR

    docs_config = load_docs_config(repo_root)
    if args.strict_config and docs_config.get("configError"):
        print(f"ERROR: {docs_config['configError']}")
        if docs_config.get("configPath"):
            print(f"Config path: {docs_config['configPath']}")
        return EXIT_INPUT_ERROR

    try:
        if args.base_ref:
            changed_paths = collect_ref_diff_changes(repo_root, args.base_ref, args.head_ref)
            source_label = f"{args.base_ref}...{args.head_ref}"
        else:
            changed_paths = collect_working_tree_changes(repo_root)
            source_label = "working tree + untracked"
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return EXIT_GIT_ERROR

    evaluation = evaluate_docs_freshness(changed_paths, docs_config)

    print("Documentation Freshness Check")
    print(f"Repo root: {repo_root}")
    print(f"Change source: {source_label}")
    print(f"Changed paths: {len(evaluation['changedPaths'])}")
    if docs_config.get("configPath"):
        print(f"Docs config: {docs_config['configPath']}")
    else:
        print("Docs config: default (README.md files + docs/)")
    if docs_config.get("configError"):
        print(f"Config warning: {docs_config['configError']}")

    if not evaluation["changedPaths"]:
        print("PASS: No changed files detected.")
        return EXIT_OK

    if evaluation["needsDocumentationReview"]:
        print("FAIL: Documentation is stale for changed non-doc areas.")
        print("Missing documentation areas:")
        for area in evaluation["missingDocumentationAreas"]:
            print(f"- {area}")
        print("Hint: update README.md in each missing area, or docs/ for shared docs updates.")
        return EXIT_STALE_DOCS

    print("PASS: Documentation freshness check passed.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())