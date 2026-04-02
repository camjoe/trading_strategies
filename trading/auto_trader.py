# Architecture: compatibility shim — import from canonical location instead:
#   trading.interfaces.runtime.jobs.daily_auto_trader
from trading.profile_source import DEFAULT_TICKERS_FILE  # re-exported for tests
from trading.interfaces.runtime.jobs.daily_auto_trader import (
    build_iv_rank_proxy,
    fetch_latest_prices,
    load_tickers_from_file,
    ensure_db,
    main,
    parse_args,
    run_for_account,
)

__all__ = [
    "DEFAULT_TICKERS_FILE",
    "build_iv_rank_proxy",
    "ensure_db",
    "fetch_latest_prices",
    "load_tickers_from_file",
    "main",
    "parse_args",
    "run_for_account",
]

if __name__ == "__main__":
    main()
