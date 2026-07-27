"""Unified parameter source package.

The stable public surface for the read-through parameter view: one legible
place over the existing stores (global settings, per-book settings tables,
strategy rows) — deliberately a view, not a new consolidated store. Concrete
logic lives in focused modules beneath this package root.
"""

from __future__ import annotations

from trading.services.parameters.history import fetch_book_rotation_change_history
from trading.services.parameters.mutations import (
    ROTATION_POLICY_FIELDS,
    ROTATION_SCHEDULING_FIELDS,
    update_book_rotation_policy,
    update_book_rotation_scheduling,
)
from trading.services.parameters.presentation import show_book_rotation_history, show_parameters
from trading.services.parameters.view import fetch_parameter_source_view

__all__ = [
    "ROTATION_POLICY_FIELDS",
    "ROTATION_SCHEDULING_FIELDS",
    "fetch_book_rotation_change_history",
    "fetch_parameter_source_view",
    "show_book_rotation_history",
    "show_parameters",
    "update_book_rotation_policy",
    "update_book_rotation_scheduling",
]
