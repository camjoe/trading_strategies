"""Compatibility shim for the canonical runtime data-ops CSV export module."""

import sys

from trading.interfaces.runtime.data_ops import csv_export as _csv_export

sys.modules[__name__] = _csv_export
