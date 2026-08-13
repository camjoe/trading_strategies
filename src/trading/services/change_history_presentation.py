"""Shared presentation for settings change-audit history.

The global-settings and book-rotation change-audit trails render each event the
same way. This module owns that shared per-event rendering; the package-level
``show_*`` wrappers add their own header and empty-state text.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class SettingsChangeEvent(Protocol):
    """The change-audit event shape both settings histories share.

    Read-only members so frozen event dataclasses satisfy the protocol.
    """

    @property
    def settings_group(self) -> str: ...

    @property
    def changed_fields(self) -> dict[str, dict[str, object]]: ...

    @property
    def created_at(self) -> str: ...


def render_settings_change_lines(events: Sequence[SettingsChangeEvent]) -> list[str]:
    lines: list[str] = []
    for event in events:
        rendered = ", ".join(
            f"{field}: {change['old']!r} -> {change['new']!r}" for field, change in event.changed_fields.items()
        )
        lines.append(f"- {event.created_at} | {event.settings_group} | {rendered}")
    return lines


__all__ = ["SettingsChangeEvent", "render_settings_change_lines"]
