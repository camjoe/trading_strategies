"""Domain-level exceptions for the trading package.

Placed in the domain layer so every layer at or above it can raise or catch
them without importing upward or reaching into ``trading.repositories`` /
``infrastructure``. Domain policy raises ``ValidationError`` (see
``strategies.resolution``); services raise the rest. The UI maps these types to
HTTP status codes — see ``docs/adr/007-ui-error-mapping.md``.
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


class ValidationError(ValueError):
    """Raised by domain policy or the service layer when input fails validation.

    Subclasses ``ValueError`` deliberately, for the same reason as
    ``NotFoundError``: existing ``except ValueError`` handlers (CLI dispatch, UI
    validation catches, tests) keep working unchanged, while the UI can match
    this type to map bad input to HTTP 400/422. A bare ``ValueError`` still
    signals an unexpected error (HTTP 500), not a validation failure. See
    ``docs/adr/007-ui-error-mapping.md``.
    """


class AccountAlreadyExistsError(Exception):
    """Raised by ``create_account`` when the account name is already taken."""


class RuntimeTradeThrottleExceededError(Exception):
    """Raised when a persisted global runtime trade throttle blocks another auto-trade."""
