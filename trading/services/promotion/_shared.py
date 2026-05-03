"""Shared promotion helpers for internal promotion modules.

Provides small formatting and normalization helpers used across the promotion
service split under ``trading.services.promotion``.
"""

from __future__ import annotations

YES_TEXT = "yes"
NO_TEXT = "no"
NONE_TEXT = "none"


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def render_bool(value: bool) -> str:
    return YES_TEXT if value else NO_TEXT


def render_section(title: str, items: list[str]) -> list[str]:
    lines = [f"{title}:"]
    if not items:
        lines.append(f"- {NONE_TEXT}")
        return lines
    for item in items:
        lines.append(f"- {item}")
    return lines
