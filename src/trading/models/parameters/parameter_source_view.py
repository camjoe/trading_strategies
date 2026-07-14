from __future__ import annotations

from dataclasses import dataclass

from trading.models.parameters.parameter_group import ParameterGroup


@dataclass(frozen=True, slots=True)
class ParameterSourceView:
    """The unified parameter source view: a read-through payload over the
    existing stores (global settings, book settings, strategy rows) — a view,
    not a new store."""

    groups: tuple[ParameterGroup, ...]
