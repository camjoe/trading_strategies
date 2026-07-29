"""Apply broker fills to the books for one or more accounts.

Paper accounts fill synchronously and have no open broker orders, so this is a
no-op for them. It exists for the async broker paths (the IBKR socket/TWS
adapter): orders come back ``SUBMITTED`` and their fills arrive later, so
something has to poll the broker and write those fills into
``order_fills``/positions/ledger before equity is snapshotted.

The daily workflow runs this before each of its snapshot passes.
"""

from __future__ import annotations

import argparse
import sys

from infrastructure.brokers.factory import get_broker_for_account
from infrastructure.database.connection import db_session
from trading.services.accounts import get_account
from trading.services.auto_trading import reconcile_open_broker_orders

__all__ = ["main", "parse_args"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply outstanding broker fills to the books.")
    parser.add_argument(
        "--accounts",
        required=True,
        help="Comma-separated account names, e.g. momentum_5k,meanrev_5k",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    account_names = [name.strip() for name in args.accounts.split(",") if name.strip()]

    with db_session() as conn:
        for account_name in account_names:
            account = get_account(conn, account_name)
            outcome = reconcile_open_broker_orders(
                conn,
                account,
                broker_factory=get_broker_for_account,
            )
            print(f"{account_name}: reconciled {outcome.newly_filled} newly filled order(s)")
            if outcome.has_unreported:
                # Left open deliberately: an unreported order may have expired
                # unfilled or may have filled on a day nothing ran, and guessing
                # wrong would corrupt the book. An operator has to decide.
                ids = ", ".join(outcome.unreported_broker_order_ids)
                print(
                    f"{account_name}: WARNING {len(outcome.unreported_broker_order_ids)} open order(s) "
                    f"not reported by the broker and left unresolved: {ids}",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    main()
