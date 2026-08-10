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
            if outcome.adopted_pending:
                print(
                    f"{account_name}: adopted {outcome.adopted_pending} order(s) the broker was "
                    f"carrying but this database had only as pending"
                )
            if outcome.has_unresolved_pending:
                # Sent, and the broker's order list does not carry it. It may have
                # been rejected on the way in, or filled and already aged off the
                # list — the difference matters to the book, so an operator checks.
                ids = ", ".join(outcome.unresolved_pending_client_order_ids)
                print(
                    f"{account_name}: WARNING {len(outcome.unresolved_pending_client_order_ids)} order(s) "
                    f"were sent but never confirmed and no live broker order claims them: {ids}",
                    file=sys.stderr,
                )
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
