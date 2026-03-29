from __future__ import annotations

import html
import json
import re
from pathlib import Path


GLOSSARY_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
TABLE_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")

UI_SECTION_RE = re.compile(
    r"<h3>(.*?)</h3>.*?<tbody>(.*?)</tbody>",
    re.DOTALL | re.IGNORECASE,
)
UI_ROW_RE = re.compile(r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>", re.DOTALL | re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")


TERM_ALIASES = {
    "dte (days to expiration)": "DTE",
}


def normalize_term(raw: str) -> str:
    cleaned = " ".join(raw.split()).strip()
    alias = TERM_ALIASES.get(cleaned.lower())
    return alias if alias else cleaned


def parse_glossary(glossary_path: Path) -> dict[str, tuple[str, str]]:
    lines = glossary_path.read_text(encoding="utf-8").splitlines()
    current_section = ""
    terms: dict[str, tuple[str, str]] = {}

    for line in lines:
        section_match = GLOSSARY_SECTION_RE.match(line)
        if section_match:
            current_section = section_match.group(1).strip()
            continue

        row_match = TABLE_ROW_RE.match(line)
        if not row_match:
            continue

        left = row_match.group(1).strip()
        right = row_match.group(2).strip()
        if left.lower() in {"term", "concept"}:
            continue
        if set(left) == {"-"} or set(right) == {"-"}:
            continue

        normalized = normalize_term(left)
        if not normalized:
            continue
        terms[normalized] = (current_section, right)

    return terms


def strip_html(value: str) -> str:
    text = html.unescape(value)
    text = HTML_TAG_RE.sub("", text)
    return " ".join(text.split()).strip()


def extract_financial_card_body(raw: str) -> str:
    heading = "<h2>Financial &amp; Market Knowledge</h2>"
    heading_index = raw.find(heading)
    if heading_index == -1:
        return ""

    start_index = raw.rfind('<section class="card ref-card">', 0, heading_index)
    if start_index == -1:
        return ""

    next_card_index = raw.find('\n  <section class="card ref-card">', heading_index)
    if next_card_index == -1:
        return raw[start_index:]
    return raw[start_index:next_card_index]


def parse_ui_terms(ui_docs_path: Path) -> dict[str, tuple[str, str]]:
    raw = ui_docs_path.read_text(encoding="utf-8")
    no_comments = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)

    card_body = extract_financial_card_body(no_comments)
    if not card_body:
        return {}

    terms: dict[str, tuple[str, str]] = {}

    for section_match in UI_SECTION_RE.finditer(card_body):
        section_name = strip_html(section_match.group(1))
        table_body = section_match.group(2)

        for row_match in UI_ROW_RE.finditer(table_body):
            raw_term = strip_html(row_match.group(1))
            raw_definition = strip_html(row_match.group(2))
            normalized = normalize_term(raw_term)
            if not normalized:
                continue
            terms[normalized] = (section_name, raw_definition)

    return terms


def load_existing_state(registry_path: Path) -> tuple[dict[str, dict[str, str]], bool]:
    if not registry_path.exists():
        return {}, True
    try:
        existing = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, True

    schema_version = existing.get("schema_version", 0)
    uses_surface_semantics = existing.get("use_semantics") == "surfaces"

    state: dict[str, dict[str, str]] = {}
    for term in existing.get("terms", []):
        term_name = term.get("term")
        if not isinstance(term_name, str):
            continue

        if not uses_surface_semantics and schema_version < 2:
            glossary_def = term.get("glossary") or term.get("glossary_definition")
            ui_def = term.get("ui") or term.get("ui_definition")
            if isinstance(glossary_def, str) and isinstance(ui_def, str):
                state[term_name] = {
                    "use": "both",
                    "group": str(term.get("group") or term.get("glossary_section") or term.get("ui_section") or ""),
                    "definition": str(term.get("definition") or glossary_def),
                }
                continue
            if isinstance(glossary_def, str):
                state[term_name] = {
                    "use": "glossary",
                    "group": str(term.get("group") or term.get("glossary_section") or ""),
                    "definition": str(term.get("definition") or glossary_def),
                }
                continue
            if isinstance(ui_def, str):
                state[term_name] = {
                    "use": "ui",
                    "group": str(term.get("group") or term.get("ui_section") or ""),
                    "definition": str(term.get("definition") or ui_def),
                }
                continue

        source = term.get("use") or term.get("use_definition") or term.get("canonical_source")
        if source in {"both", "glossary", "ui"}:
            state[term_name] = {
                "use": str(source),
                "group": str(term.get("group") or ""),
                "definition": str(term.get("definition") or ""),
            }
    return state, uses_surface_semantics


def build_registry(
    glossary_terms: dict[str, tuple[str, str]],
    ui_terms: dict[str, tuple[str, str]],
    existing_state: dict[str, dict[str, str]],
    uses_surface_semantics: bool,
) -> list[dict[str, object]]:
    merged_terms = sorted(set(glossary_terms) | set(ui_terms) | set(existing_state), key=str.lower)
    rows: list[dict[str, object]] = []

    for term in merged_terms:
        glossary = glossary_terms.get(term)
        ui = ui_terms.get(term)
        existing = existing_state.get(term, {})

        has_glossary = glossary is not None
        has_ui = ui is not None

        valid_uses: set[str] = set()
        if has_glossary and has_ui:
            valid_uses = {"both", "glossary", "ui"}
        elif has_glossary:
            valid_uses = {"glossary"}
        elif has_ui:
            valid_uses = {"ui"}

        chosen = existing.get("use")
        if chosen not in valid_uses:
            if has_glossary and has_ui:
                chosen = "both"
            elif has_glossary:
                chosen = "glossary"
            else:
                chosen = "ui"

        if not uses_surface_semantics and has_glossary and has_ui and chosen in {"glossary", "ui"}:
            chosen = "both"

        default_group = glossary[0] if glossary else (ui[0] if ui else "(unsectioned)")
        group = str(existing.get("group") or default_group)
        use_rank = {"both": 0, "glossary": 1, "ui": 2}[chosen]
        default_definition = glossary[1] if glossary else (ui[1] if ui else "")
        definition = str(existing.get("definition") or default_definition)

        row = {
            "term": term,
            "group": group,
            "use": chosen,
            "definition": definition,
            "_sort": [use_rank, group.lower(), term.lower()],
        }
        rows.append(row)

    rows.sort(key=lambda item: tuple(item["_sort"]))
    for row in rows:
        del row["_sort"]
    return rows