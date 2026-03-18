import sys

from trading.features.backtesting import strategy_signals as _impl

sys.modules[__name__] = _impl
