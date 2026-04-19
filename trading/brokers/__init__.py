"""Broker abstraction layer.

Provides a uniform interface over paper and live broker connections.
Concrete adapters live alongside this package:
  - paper_adapter.py  — simulated immediate-fill broker (default)
  - ib_adapter.py     — Interactive Brokers live adapter (requires TWS or IB Gateway)
  - ib_web_adapter.py — Interactive Brokers Web API adapter (Client Portal / Campus Web API)
  - ib_client.py      — IBClientProtocol + IbAsyncClient (default) + IbApiClient (stub)
  - factory.py        — resolves the correct BrokerConnection for an account row
"""
