from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParameterEntry:
    """One named parameter with its rendered effective value.

    ``value`` is the display rendering ("none" for unset optionals);
    ``source`` uses the PARAMETER_SOURCE_* vocabulary.
    """

    name: str
    value: str
    source: str
