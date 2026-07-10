from __future__ import annotations

from dataclasses import dataclass

from trading.models.parameters.parameter_entry import ParameterEntry


@dataclass(frozen=True, slots=True)
class ParameterGroup:
    """One scoped group of parameters in the unified view.

    ``scope`` is the human-readable path (e.g. "global / trade throttle",
    "account alpha / book default / execution"). ``note`` carries a
    group-level remark such as the code-defaults fallback when no settings
    row exists.
    """

    scope: str
    entries: tuple[ParameterEntry, ...]
    note: str | None = None
