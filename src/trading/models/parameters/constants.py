"""Data-contract vocabulary for the unified parameter source view."""

from __future__ import annotations

# Where a parameter group's effective value comes from: a persisted settings
# row (`db`), or code (`default`) — either a code default because no row exists,
# or a code-owned attribute like a primitive's style that is never persisted.
PARAMETER_SOURCE_DB = "db"
PARAMETER_SOURCE_DEFAULT = "default"
