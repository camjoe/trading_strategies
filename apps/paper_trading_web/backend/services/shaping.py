"""snake_case -> camelCase key shaping for JSON responses.

The ``src/trading`` analysis/service layer returns snake_case domain payloads;
the HTTP boundary shapes them into the frontend's camelCase. Keeping this
transform here (not in ``src/trading``) honours the UI Backend Boundary Rule:
UI-shaping lives at the web backend boundary only.
"""

from __future__ import annotations

from typing import Any


def _to_camel(key: str) -> str:
    head, *rest = key.split("_")
    return head + "".join(word[:1].upper() + word[1:] for word in rest)


def camelize_keys(value: Any) -> Any:
    """Recursively convert dict keys from snake_case to camelCase.

    Nested dicts and lists are transformed; scalars (and ``None``) pass through
    unchanged. Values are never renamed — only mapping keys.
    """
    if isinstance(value, dict):
        return {_to_camel(str(key)): camelize_keys(item) for key, item in value.items()}
    if isinstance(value, list):
        return [camelize_keys(item) for item in value]
    return value


__all__ = ["camelize_keys"]
