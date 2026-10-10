"""Broker abstraction layer.

Provides a uniform interface over paper and live broker connections.
Concrete adapters live in this package:
  - paper_adapter.py  — simulated immediate-fill broker (default)
  - ibkr_web/         — Interactive Brokers Client Portal / Web API
  - ibkr_socket/      — Interactive Brokers TWS / IB Gateway socket API
  - factory.py        — resolves the correct BrokerConnection for an account

This package is injected at the interface layer
(``trading/interfaces/runtime/jobs/daily/paper_trading/run_auto_trades.py``).
``trading/`` must never import directly from ``brokers/``.
"""

from __future__ import annotations
