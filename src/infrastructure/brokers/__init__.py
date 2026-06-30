"""Broker abstraction layer.

Provides a uniform interface over paper and live broker connections.
Concrete adapters live alongside this package:
  - paper_adapter.py  — simulated immediate-fill broker (default)
  - ib_web_adapter.py — Interactive Brokers Web API adapter (Client Portal / Campus Web API)
  - factory.py        — resolves the correct BrokerConnection for an account

Legacy socket/TWS support lives under ``brokers/legacy/``.

This package is injected at the interface layer
(``trading/interfaces/runtime/jobs/daily/paper_trading/run_auto_trades.py``).
``trading/`` must never import directly from ``brokers/``.
"""

from __future__ import annotations
