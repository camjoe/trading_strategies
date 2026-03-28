"""Compatibility shim for the canonical runtime data-ops admin module."""

import sys

from trading.interfaces.runtime.data_ops import admin as _admin

sys.modules[__name__] = _admin
