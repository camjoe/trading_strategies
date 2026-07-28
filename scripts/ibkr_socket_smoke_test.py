"""Manual smoke test for the IBKR socket/TWS integration.

Operator-run only. It connects the socket adapter straight to a locally running
TWS or IB Gateway and performs read-only checks:

- connect / is-connected
- account summary fetch
- positions fetch
- open-trade fetch
- optional snapshot quotes for a few tickers

It deliberately takes host/port/client-id as flags rather than reading an
account row, so it can be run *before* any account is pointed at the socket
path. It never places an order and never touches the database.

Default ports: TWS paper 7497, TWS live 7496, IB Gateway paper 4002, IB Gateway
live 4001. Point this at a paper port.
"""

from __future__ import annotations

import argparse
import sys
from typing import TextIO

from infrastructure.brokers.ibkr_socket.adapter import IbkrSocketAdapter
from infrastructure.brokers.ibkr_socket.factory import resolve_ibkr_socket_client_backend
from infrastructure.brokers.ibkr_socket.ib_async_client import IbAsyncClient
from infrastructure.brokers.ibkr_socket.ibapi_client import IbApiClient

# TWS paper trading port — the safe default for a smoke test.
_DEFAULT_PORT = 7497

# A client id distinct from the runtime's default (1) so a smoke test can run
# alongside a live session without the broker rejecting a duplicate id.
_DEFAULT_CLIENT_ID = 99


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a read-only IBKR socket/TWS smoke test against a local TWS or IB Gateway.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="TWS/Gateway host (default: 127.0.0.1)")
    parser.add_argument(
        "--port",
        type=int,
        default=_DEFAULT_PORT,
        help=f"TWS/Gateway port (default: {_DEFAULT_PORT} = TWS paper; IB Gateway paper is 4002)",
    )
    parser.add_argument(
        "--client-id",
        type=int,
        default=_DEFAULT_CLIENT_ID,
        help=f"API client id (default: {_DEFAULT_CLIENT_ID})",
    )
    parser.add_argument(
        "--quote-tickers",
        default="",
        help="Optional comma-separated tickers to request snapshot quotes for (example: AAPL,MSFT)",
    )
    return parser.parse_args()


def build_adapter(host: str, port: int, client_id: int) -> IbkrSocketAdapter:
    """Build the adapter using the same backend selection the broker factory uses."""
    backend = resolve_ibkr_socket_client_backend()
    client = IbApiClient() if backend == "ibapi" else IbAsyncClient()
    return IbkrSocketAdapter(client=client, host=host, port=port, client_id=client_id)


def run_smoke_test(args: argparse.Namespace, out: TextIO = sys.stdout) -> int:
    backend = resolve_ibkr_socket_client_backend()
    print(f"backend            : {backend}", file=out)
    print(f"target             : {args.host}:{args.port} client_id={args.client_id}", file=out)

    adapter = build_adapter(args.host, args.port, args.client_id)
    try:
        adapter.connect()
    except Exception as exc:
        print(f"FAIL connect       : {type(exc).__name__}: {exc}", file=out)
        print("Is TWS/IB Gateway running with the API enabled on this port?", file=out)
        return 1

    try:
        print("connect            : ok", file=out)

        account_info = adapter.get_account_info()
        print(f"account summary    : {account_info}", file=out)

        positions = adapter.get_positions()
        print(f"positions          : {len(positions)} symbol(s) {positions}", file=out)

        open_trades = adapter.get_open_trades()
        print(f"open trades        : {len(open_trades)}", file=out)
        for trade in open_trades:
            print(
                f"  - {trade.ticker} {trade.side} qty={trade.qty} "
                f"status={trade.status} filled={trade.filled_qty} id={trade.broker_order_id}",
                file=out,
            )

        tickers = [item.strip().upper() for item in args.quote_tickers.split(",") if item.strip()]
        if tickers:
            quotes = adapter.get_quotes(tickers)
            print(f"quotes             : {quotes}", file=out)
    except Exception as exc:
        print(f"FAIL read          : {type(exc).__name__}: {exc}", file=out)
        return 1
    finally:
        adapter.disconnect()
        print("disconnect         : ok", file=out)

    print("\nPASS: socket path is reachable and read-only calls succeeded.", file=out)
    return 0


def main() -> int:
    return run_smoke_test(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
