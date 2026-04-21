"""Stable public facade for account-related service helpers.

External callers should keep importing from ``trading.services.accounts_service``.
The ``trading.services.accounts.*`` package is the implementation split used to
organize listing, config, and mutation responsibilities internally.

This module also re-exports domain constants and ``AccountAlreadyExistsError`` so
that callers never need to reach into domain or config sub-packages directly:

- ``DEFAULT_MAX_POSITION_PCT``, ``DEFAULT_TRADE_SIZE_PCT`` — default position-sizing
  constants from ``trading.domain.auto_trader_policy``.
- ``parse_rotation_schedule``, ``parse_rotation_overlay_watchlist``,
  ``OPTIMALITY_MODES``, ``ROTATION_MODES``, ``ROTATION_OVERLAY_MODES`` — rotation
  config parsers and allowed-value sets from ``trading.domain.rotation``.
- ``INSTRUMENT_MODES``, ``OPTION_TYPES``, ``RISK_POLICIES`` — account config
  allowed-value sets from ``trading.services.accounts.config``.
- ``AccountAlreadyExistsError`` — domain exception raised on duplicate account
  creation, from ``trading.domain.exceptions``.
"""

from __future__ import annotations
from trading.services.accounts.listing import (  # noqa: F401
    GOAL_NOT_SET_TEXT,
    build_account_listing_lines,
    format_account_policy_text,
    format_goal_text,
    list_accounts,
)
from trading.services.accounts.mutations import (  # noqa: F401
    configure_account,
    create_account,
    get_account,
    set_account_strategy,
    set_benchmark,
)
from trading.services.accounts.queries import (  # noqa: F401
    find_account,
    get_latest_account_snapshot,
    list_account_names,
    list_account_records,
    list_account_snapshots,
    load_all_account_names,
)

# Re-exported for callers that should not reach into domain directly.
from trading.domain.exceptions import AccountAlreadyExistsError  # noqa: F401
from trading.domain.auto_trader_policy import (  # noqa: F401
    DEFAULT_MAX_POSITION_PCT,
    DEFAULT_TRADE_SIZE_PCT,
)
from trading.domain.rotation import (  # noqa: F401
    parse_rotation_overlay_watchlist,
    parse_rotation_schedule,
    OPTIMALITY_MODES,
    ROTATION_MODES,
    ROTATION_OVERLAY_MODES,
)
from trading.services.accounts.config import (  # noqa: F401
    ACCOUNT_KINDS,
    ACCOUNT_KIND_LOCAL,
    ACCOUNT_KIND_MANAGED,
    ACCOUNT_KIND_TEST_SHADOW,
    INSTRUMENT_MODES,
    OPTION_TYPES,
    RISK_POLICIES,
)
