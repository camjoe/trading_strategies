"""Text normalization shared by the promotion mutation and history modules."""

from __future__ import annotations


def normalize_optional_text(value: str | None) -> str | None:
    """Strip a caller-supplied string, reading blank as absent."""
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
