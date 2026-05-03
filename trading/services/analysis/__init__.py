"""Analysis service package.

This package is the stable public analysis surface. Concrete logic lives in
focused modules beneath this package root.
"""

from trading.services.analysis.queries import fetch_account_analysis

__all__ = [
    "fetch_account_analysis",
]
