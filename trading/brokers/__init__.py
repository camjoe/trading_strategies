"""Broker abstraction layer.

Provides a uniform interface over paper and live broker connections.
Concrete adapters live alongside this package:
  - paper_adapter.py  — simulated immediate-fill broker (default)
  - ib_web_adapter.py — Interactive Brokers Web API adapter (Client Portal / Campus Web API)
  - factory.py        — resolves the correct BrokerConnection for an account row

Legacy socket/TWS support lives under ``trading/brokers/legacy/``.
"""
