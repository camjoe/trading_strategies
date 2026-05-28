"""External-data feature providers.

This package contains concrete external-data feature providers used by
``strategy_style = "alternative"`` strategies. All third-party API calls,
SDK imports, caching, and data normalization live here, while shared
contracts stay in ``trading.domain.feature_provider``.
"""

from __future__ import annotations
