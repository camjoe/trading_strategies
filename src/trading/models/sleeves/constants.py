"""Sleeve risk-gate default limit values for :class:`SleeveRiskGateConfig`.

Callers may override any of these per evaluation.  They live in the models layer
because they are the data-contract defaults the config carries, mirroring how
``SleeveRotationScoreWeights`` keeps its default weights.

The symbol→sector reference data is *not* here: it is operator-editable config
loaded from ``src/infrastructure/config/symbol_sectors.json`` and injected at the
service layer (see ``trading.services.sleeves.sector_config``).
"""

from __future__ import annotations

# Default share of a sleeve's equity that any single symbol position may occupy.
DEFAULT_MAX_SLEEVE_NOTIONAL_PCT = 0.25
# Default share of total portfolio equity that any single symbol may occupy.
DEFAULT_MAX_SYMBOL_CONCENTRATION_PCT = 0.30
# Default cap on gross exposure as a multiple of total portfolio equity.
DEFAULT_MAX_PORTFOLIO_GROSS_EXPOSURE = 1.0
# Default share of total portfolio equity that any single sector may occupy.
DEFAULT_MAX_SECTOR_CONCENTRATION_PCT = 0.45
