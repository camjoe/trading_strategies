"""Area-scoped test support package.

Import helpers from their specific module, for example:

- ``tests.support.auto_trading``
- ``tests.support.backtesting``
- ``tests.support.runtime_jobs``
- ``tests.support.seed.db``

CLI test helpers (``FakeConn``, ``install_main_harness``, backtest arg factories)
live co-located with the CLI tests in ``tests.trading.interfaces.cli``:

- ``tests.trading.interfaces.cli.helpers``
- ``tests.trading.interfaces.cli.factories``

This package intentionally avoids acting as a catch-all re-export surface.
"""

__all__: list[str] = []
