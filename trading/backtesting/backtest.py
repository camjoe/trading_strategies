import sys

from trading.features.backtesting import backtest as _impl

sys.modules[__name__] = _impl
