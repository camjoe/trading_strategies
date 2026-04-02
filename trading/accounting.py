# Architecture: compatibility shim — import from canonical locations instead:
#   pure logic  -> trading.domain.accounting
#   trade I/O   -> trading.services.accounting_service
from common.time import utc_now_iso  # re-exported so existing string monkeypatches on this module still work
from trading.domain.accounting import VALID_SIDES, compute_account_state
from trading.services.accounting_service import load_trades, record_trade

__all__ = [
    "VALID_SIDES",
    "compute_account_state",
    "load_trades",
    "record_trade",
    "utc_now_iso",
]
