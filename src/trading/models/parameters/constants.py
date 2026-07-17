"""Data-contract vocabulary for the unified parameter source view."""

from __future__ import annotations

# Where a parameter group's effective values come from: a persisted settings
# row, or code defaults because no row exists.
PARAMETER_SOURCE_DB = "db"
PARAMETER_SOURCE_DEFAULT = "default"
