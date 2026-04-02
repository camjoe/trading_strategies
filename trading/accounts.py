# Architecture: compatibility shim — import from trading.services.accounts_service instead.
from trading.services.accounts_service import (
    INSTRUMENT_MODES,
    OPTION_TYPES,
    RISK_POLICIES,
    configure_account,
    create_account,
    get_account,
    list_accounts,
    load_all_account_names,
    set_benchmark,
)

__all__ = [
    "INSTRUMENT_MODES",
    "OPTION_TYPES",
    "RISK_POLICIES",
    "configure_account",
    "create_account",
    "get_account",
    "list_accounts",
    "load_all_account_names",
    "set_benchmark",
]
