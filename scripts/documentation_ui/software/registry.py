from __future__ import annotations

import json
from pathlib import Path

from scripts.documentation_ui.registry_utils import sort_registry_rows


SOFTWARE_REGISTRY_REL = "paper_trading_ui/frontend/src/assets/software.json"



GROUP_ORDER = [
    "Data & Market Access",
    "Analysis & Modeling",
    "Visualization",
    "Backend & Validation",
    "Developer Tooling",
]

GROUP_BY_PACKAGE = {
    "fastapi": "Backend & Validation",
    "ib_async": "Data & Market Access",
    "httpx": "Developer Tooling",
    "hypothesis": "Developer Tooling",
    "matplotlib": "Visualization",
    "newsapi-python": "Data & Market Access",
    "numpy": "Analysis & Modeling",
    "pandas": "Analysis & Modeling",
    "playwright": "Developer Tooling",
    "praw": "Data & Market Access",
    "pydantic": "Backend & Validation",
    "pytest": "Developer Tooling",
    "pytest-cov": "Developer Tooling",
    "pytest-mock": "Developer Tooling",
    "pytest-xdist": "Developer Tooling",
    "python-dotenv": "Backend & Validation",
    "pytrends": "Data & Market Access",
    "uvicorn": "Backend & Validation",
    "vadersentiment": "Analysis & Modeling",
    "yfinance": "Data & Market Access",
}

PURPOSE_BY_PACKAGE = {
    "ib_async": "Async Interactive Brokers client used for broker connectivity, live account queries, and order execution flows.",
    "newsapi-python": "News API client used by alternative strategy features to fetch news inputs for sentiment-style signals.",
    "playwright": "Browser automation library used for UI smoke checks and end-to-end interaction coverage.",
    "praw": "Reddit API client used by alternative strategy features to fetch social discussion inputs.",
    "pytest-xdist": "Parallel test execution plugin used to speed up larger local and CI pytest runs.",
    "pytrends": "Google Trends client used by alternative strategy features to pull search-interest signals.",
    "vadersentiment": "Rule-based sentiment scoring library used to convert fetched text into lightweight sentiment features.",
}


def normalize_package_name(raw: str) -> str:
    cleaned = " ".join(raw.split()).strip()
    base = cleaned.split("[", 1)[0]
    return base.lower()


def parse_requirement_entry(raw: str) -> tuple[str, str] | None:
    line = raw.strip()
    if not line or line.startswith("#") or line.startswith("-r"):
        return None

    for marker in ("==", ">=", "<=", "~=", "!=", ">", "<"):
        if marker in line:
            name, remainder = line.split(marker, 1)
            return name.strip(), f"{marker}{remainder.strip()}"
    return line, ""


def parse_requirements_file(path: Path, scope: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_requirement_entry(line)
        if parsed is None:
            continue
        display_name, version = parsed
        key = normalize_package_name(display_name)
        rows[key] = {
            "name": display_name,
            "version": version,
            "scope": scope,
        }
    return rows


def parse_requirements(base_path: Path, dev_path: Path) -> dict[str, dict[str, str]]:
    rows = parse_requirements_file(base_path, scope="runtime")
    for key, value in parse_requirements_file(dev_path, scope="development").items():
        if key not in rows:
            rows[key] = value
    return rows


def load_existing_state(registry_path: Path) -> dict[str, dict[str, str]]:
    if not registry_path.exists():
        return {}
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    rows: dict[str, dict[str, str]] = {}
    for item in payload.get("packages", []):
        name = item.get("name")
        if not isinstance(name, str):
            continue
        rows[normalize_package_name(name)] = {
            "group": str(item.get("group") or ""),
            "purpose": str(item.get("purpose") or ""),
        }
    return rows


def build_registry(
    parsed_requirements: dict[str, dict[str, str]],
    existing_state: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key in sorted(parsed_requirements, key=str.lower):
        package = parsed_requirements[key]
        existing = existing_state.get(key, {})
        default_group = GROUP_BY_PACKAGE.get(key, "Backend & Validation")
        group = existing.get("group") or default_group
        if group == "Backend & Validation" and default_group != "Backend & Validation":
            group = default_group
        purpose = existing.get("purpose") or PURPOSE_BY_PACKAGE.get(key, "")
        group_rank = GROUP_ORDER.index(group) if group in GROUP_ORDER else len(GROUP_ORDER)
        rows.append(
            {
                "name": package["name"],
                "version": package["version"],
                "scope": package["scope"],
                "group": group,
                "purpose": purpose,
                "_sort_group": str(group_rank),
            }
        )

    sort_registry_rows(rows, lambda item: item["name"].lower())
    return rows
