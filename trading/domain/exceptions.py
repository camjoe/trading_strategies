"""Domain-level exceptions for the trading package.

These are raised by the service layer so that callers (UI routes, CLI
interfaces, tests) never need to import from lower-level packages such as
``trading.database`` or ``trading.repositories``.
"""
from __future__ import annotations


class AccountAlreadyExistsError(Exception):
    """Raised by ``create_account`` when the account name is already taken."""
