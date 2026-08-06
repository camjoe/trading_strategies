"""Kill-switch reasons and safety thresholds for the shared execution path.

Owned centrally so every book inherits the same guards.
"""

from __future__ import annotations

# --- pre-submit kill-switch reasons (owned by the gate) ---------------------

# Required price marks are unavailable or invalid for an approved intent.
KILL_SWITCH_REASON_STALE_PRICE_DATA = "stale_price_data"
# Book-equity roll-up disagrees with the latest account snapshot beyond tolerance.
KILL_SWITCH_REASON_RECONCILIATION_MISMATCH = "reconciliation_mismatch"
# No account snapshot exists to reconcile against.
KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING = "reconciliation_snapshot_missing"

# --- submission-time kill-switch reason (owned by the submission service) ---

# Broker submission raised an exception mid-loop.
KILL_SWITCH_REASON_BROKER_API_ANOMALY = "broker_api_anomaly"

# --- reconciliation thresholds ----------------------------------------------

# Absolute equity tolerance for the book-vs-snapshot reconciliation check. This is
# also what enforces snapshot freshness: books are marked to current prices just
# before the comparison, so a stale snapshot fails on value. See
# `reconciliation.py` for why there is no separate age bound.
RECONCILIATION_EQUITY_TOLERANCE = 0.01
