"""Alt-strategy feature-provider service surface.

This package keeps route handlers thin by centralizing provider loading,
status probing, and feature-only signal evaluation.
"""

from __future__ import annotations

from .signals import get_signals
from .status import get_provider_status

__all__ = [
    "get_provider_status",
    "get_signals",
]
