"""Data-contract vocabulary for portfolio rollup payloads."""

from __future__ import annotations

# Sector bucket for symbols missing from the symbol->sector reference data
# (symbol_sectors.json); the rollup degrades gracefully instead of requiring
# full reference coverage.
UNCATEGORIZED_SECTOR = "uncategorized"
