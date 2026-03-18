import sys

from trading.features.backtesting import backtest_data as _impl

sys.modules[__name__] = _impl
