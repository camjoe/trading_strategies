"""Domain-level exceptions for the trading package.

These are raised by the service layer so that callers (UI routes, CLI
interfaces, tests) never need to import from lower-level packages such as
``trading.database`` or ``trading.repositories``.
"""

from __future__ import annotations


class NotFoundError(ValueError):
    """Raised by the service layer when a requested entity does not exist.

    Subclasses ``ValueError`` deliberately: existing ``except ValueError``
    handlers (CLI dispatch, UI validation catches, tests) keep working
    unchanged, while callers that care about not-found specifically — e.g. the
    UI's ``NotFoundError -> 404`` exception handler — can match this type. A bare
    ``ValueError`` therefore still signals an unexpected error (HTTP 500), not a
    missing entity. See ``docs/adr/007-ui-error-mapping.md``.
    """


class AccountAlreadyExistsError(Exception):
    """Raised by ``create_account`` when the account name is already taken."""


class RuntimeTradeThrottleExceededError(Exception):
    """Raised when a persisted global runtime trade throttle blocks another auto-trade."""
