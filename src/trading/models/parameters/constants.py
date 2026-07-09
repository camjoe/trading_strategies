"""Data-contract vocabulary for the unified parameter source view (P7, D4)."""

from __future__ import annotations

# Where a parameter group's effective values come from: a persisted settings
# row, or code defaults because no row exists (D4's fallback contract).
PARAMETER_SOURCE_DB = "db"
PARAMETER_SOURCE_DEFAULT = "default"
