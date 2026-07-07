"""Kill-switch reasons and safety thresholds for the shared execution path.

Owned centrally so every book inherits the same guards. The account/sleeve
routing phases (2a-3/2a-4) import these instead of the copies currently living
in ``auto_trading/runtime.py``, which are removed when the legacy paths retire.
"""

from __future__ import annotations

# --- pre-submit kill-switch reasons (owned by the gate) ---------------------

# Required price marks are unavailable or invalid for an approved intent.
KILL_SWITCH_REASON_STALE_PRICE_DATA = "stale_price_data"
# Book-equity roll-up disagrees with the latest account snapshot beyond tolerance.
KILL_SWITCH_REASON_RECONCILIATION_MISMATCH = "reconciliation_mismatch"
# No account snapshot exists to reconcile against.
KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING = "reconciliation_snapshot_missing"
# The latest account snapshot is older than the freshness threshold.
KILL_SWITCH_REASON_STALE_RECONCILIATION_SNAPSHOT = "stale_reconciliation_snapshot"

# --- submission-time kill-switch reason (owned by the submission service) ---

# Broker submission raised an exception mid-loop.
KILL_SWITCH_REASON_BROKER_API_ANOMALY = "broker_api_anomaly"

# --- reconciliation thresholds ----------------------------------------------

# Maximum allowed age for the reconciliation snapshot (seconds); 6h mirrors the
# legacy sleeve guard.
MAX_RECONCILIATION_SNAPSHOT_AGE_SECONDS = 6 * 60 * 60
# Absolute equity tolerance for the book-vs-snapshot reconciliation check.
RECONCILIATION_EQUITY_TOLERANCE = 0.01
