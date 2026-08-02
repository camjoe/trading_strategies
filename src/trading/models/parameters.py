"""Parameter-resolution data contracts."""

from __future__ import annotations

from dataclasses import dataclass

# Where a parameter group's effective value comes from: a persisted settings
# row (`db`), or code (`default`) — either a code default because no row exists,
# or a code-owned attribute like a primitive's style that is never persisted.
PARAMETER_SOURCE_DB = "db"
PARAMETER_SOURCE_DEFAULT = "default"


@dataclass(frozen=True, slots=True)
class ParameterEntry:
    """One named parameter with its rendered effective value.

    ``value`` is the display rendering ("none" for unset optionals);
    ``source`` uses the PARAMETER_SOURCE_* vocabulary.
    """

    name: str
    value: str
    source: str


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


@dataclass(frozen=True, slots=True)
class ParameterSourceView:
    """The unified parameter source view: a read-through payload over the
    existing stores (global settings, book settings, strategy rows) — a view,
    not a new store."""

    groups: tuple[ParameterGroup, ...]
