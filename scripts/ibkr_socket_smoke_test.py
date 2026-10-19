"""Manual smoke test for the IBKR socket/TWS integration.

Operator-run only. It connects the socket adapter straight to a locally running
TWS or IB Gateway and performs read-only checks:

- connect / is-connected
- managed accounts, plus whether they would pass the socket paper-venue guard
- account summary fetch
- positions fetch
- open-trade fetch
- optional snapshot quotes for a few tickers

It deliberately takes host/port/client-id as flags rather than reading an
account row, so it can be run *before* any account is pointed at the socket
path. It never touches the database.

Default ports: TWS paper 7497, TWS live 7496, IB Gateway paper 4002, IB Gateway
live 4001. Point this at a paper port.

By default nothing is submitted. `--paper-order-check` additionally places one
non-marketable limit order, watches it come back through `get_open_trades()`,
and cancels it — the round trip the fill-reconciliation path depends on. It
refuses to run against anything but a paper account.

`--fill-lookup-check` submits one MARKET order, waits for it to fill, disconnects,
reconnects, and asks the new connection for that order by id. That is the case
reconciliation meets when an order fills while no job is connected, and it is the
only way to prove `get_order` rebuilds such an order. A fractional `--fill-order-qty`
also shows whether IBKR accepts fractional sizes over the socket. It fills real
paper positions, so use a small quantity, and run it while the market is open.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from typing import TextIO

from infrastructure.brokers.factory import IBKR_PAPER_ACCOUNT_PREFIX, is_ibkr_paper_account_id
from infrastructure.brokers.ibkr_socket.adapter import IbkrSocketAdapter
from infrastructure.brokers.ibkr_socket.factory import resolve_ibkr_socket_client_backend
from infrastructure.brokers.ibkr_socket.ib_async_client import IbAsyncClient
from infrastructure.brokers.ibkr_socket.ibapi_client import IbApiClient
from trading.models.orders import BrokerOrder, OrderRequest, OrderStatus, OrderType, TimeInForce

# TWS paper trading port — the safe default for a smoke test.
_DEFAULT_PORT = 7497

# A client id distinct from the runtime's default (1) so a smoke test can run
# alongside a live session without the broker rejecting a duplicate id.
_DEFAULT_CLIENT_ID = 99

# One share is enough to prove the round trip.
_DEFAULT_PAPER_ORDER_QTY = 1.0
_DEFAULT_PAPER_ORDER_SIDE = "buy"

# Socket updates are pushed rather than polled, so a couple of short looks is
# plenty for a submitted order to surface.
_ORDER_VISIBILITY_POLL_ATTEMPTS = 3
_ORDER_VISIBILITY_POLL_DELAY_SECONDS = 2.0

# How long --fill-lookup-check waits for its market order to fill before giving up, and how often it looks.
_DEFAULT_FILL_WAIT_SECONDS = 30.0
_FILL_POLL_INTERVAL_SECONDS = 1.0

# A reported fill total and the sum of its fills may differ by float noise only.
_FILL_SUM_TOLERANCE = 1e-6

# Statuses after which an order will not fill any further.
_TERMINAL_STATUSES = frozenset({OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED})

# Statuses worth sending a cancel for. A filled or already-cancelled order is
# not, and IBKR answers a pointless cancel with an error.
_CANCELLABLE_STATUSES = frozenset(
    {
        OrderStatus.PENDING,
        OrderStatus.SUBMITTED,
        OrderStatus.ACCEPTED,
        OrderStatus.PARTIALLY_FILLED,
    }
)


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
    parser.add_argument(
        "--paper-order-check",
        action="store_true",
        help=(
            "Submit one non-marketable limit order, confirm it comes back through get_open_trades(), "
            "then cancel it. Paper accounts only — refuses to run otherwise."
        ),
    )
    parser.add_argument("--paper-order-symbol", default="", help="Ticker for --paper-order-check")
    parser.add_argument(
        "--paper-order-limit-price",
        type=float,
        default=None,
        help="Limit price for --paper-order-check. Use a clearly non-marketable price.",
    )
    parser.add_argument(
        "--paper-order-qty",
        type=float,
        default=_DEFAULT_PAPER_ORDER_QTY,
        help=f"Quantity for --paper-order-check (default: {_DEFAULT_PAPER_ORDER_QTY:g})",
    )
    parser.add_argument(
        "--paper-order-side",
        default=_DEFAULT_PAPER_ORDER_SIDE,
        choices=("buy", "sell"),
        help=f"Side for --paper-order-check (default: {_DEFAULT_PAPER_ORDER_SIDE})",
    )
    parser.add_argument(
        "--skip-paper-order-cancel",
        action="store_true",
        help="Leave the test order resting instead of cancelling it (it will expire at the close).",
    )
    parser.add_argument(
        "--fill-lookup-check",
        action="store_true",
        help=(
            "Submit one MARKET order, wait for the fill, reconnect, and look the order up by id with get_order(). "
            "Paper accounts only. Run it while the market is open."
        ),
    )
    parser.add_argument("--fill-order-symbol", default="", help="Ticker for --fill-lookup-check")
    parser.add_argument(
        "--fill-order-qty",
        type=float,
        default=None,
        help="Quantity for --fill-lookup-check; a fractional size also tests fractional support. No default.",
    )
    parser.add_argument(
        "--fill-order-side",
        default=_DEFAULT_PAPER_ORDER_SIDE,
        choices=("buy", "sell"),
        help=f"Side for --fill-lookup-check (default: {_DEFAULT_PAPER_ORDER_SIDE})",
    )
    parser.add_argument(
        "--fill-wait-seconds",
        type=float,
        default=_DEFAULT_FILL_WAIT_SECONDS,
        help=f"How long to wait for the fill (default: {_DEFAULT_FILL_WAIT_SECONDS:g})",
    )
    return parser.parse_args()


def validate_fill_lookup_args(args: argparse.Namespace) -> None:
    """Reject an incomplete fill-lookup request before anything connects."""
    if not args.fill_lookup_check:
        return
    if not str(args.fill_order_symbol).strip():
        raise ValueError("--fill-lookup-check requires --fill-order-symbol.")
    if args.fill_order_qty is None or float(args.fill_order_qty) <= 0:
        # No default: the quantity decides whether this also tests fractional sizes.
        raise ValueError("--fill-lookup-check requires a positive --fill-order-qty.")
    if float(args.fill_wait_seconds) <= 0:
        raise ValueError("--fill-wait-seconds must be greater than zero.")


def validate_paper_order_args(args: argparse.Namespace) -> None:
    """Reject an incomplete order request before anything connects."""
    if not args.paper_order_check:
        return
    if not str(args.paper_order_symbol).strip():
        raise ValueError("--paper-order-check requires --paper-order-symbol.")
    if args.paper_order_limit_price is None or float(args.paper_order_limit_price) <= 0:
        # No default: a wrong price here is the difference between an order that
        # rests where we can observe it and one that fills.
        raise ValueError("--paper-order-check requires a positive --paper-order-limit-price.")
    if float(args.paper_order_qty) <= 0:
        raise ValueError("--paper-order-qty must be greater than zero.")


def build_adapter(host: str, port: int, client_id: int) -> IbkrSocketAdapter:
    """Build the adapter using the same backend selection the broker factory uses."""
    backend = resolve_ibkr_socket_client_backend()
    client = IbApiClient() if backend == "ibapi" else IbAsyncClient()
    return IbkrSocketAdapter(client=client, host=host, port=port, client_id=client_id)


def _paper_venue_verdict(managed_accounts: list[str]) -> str:
    """Mirror the factory's socket paper guard: every account must be a paper account."""
    if not managed_accounts:
        return "WOULD BE REFUSED — no account reported, which proves nothing"
    non_paper = [account for account in managed_accounts if not is_ibkr_paper_account_id(account)]
    if non_paper:
        return (
            f"WOULD BE REFUSED — not a {IBKR_PAPER_ACCOUNT_PREFIX!r} account: {', '.join(non_paper)}. "
            "This session can trade real money; if that is intended, use the "
            "'interactive_brokers_socket' broker type and enable the live-trading flag by hand."
        )
    return f"ok — every account carries the {IBKR_PAPER_ACCOUNT_PREFIX!r} paper prefix"


def _find_trade(trades: list[BrokerOrder], broker_order_id: str) -> BrokerOrder | None:
    return next((trade for trade in trades if str(trade.broker_order_id) == str(broker_order_id)), None)


def run_paper_order_check(
    adapter: IbkrSocketAdapter,
    *,
    out: TextIO,
    symbol: str,
    side: str,
    qty: float,
    limit_price: float,
    cancel: bool,
    managed_accounts: list[str],
) -> bool:
    """Submit one resting limit order and confirm the adapter can read it back.

    This is the half of fill reconciliation that only a real broker can prove:
    an order goes out, comes back through ``get_open_trades()`` carrying a
    broker id, and can be cancelled. Applying fills to the books is the other
    half and needs a database, so it is out of scope here.

    Returns whether the round trip was verified. Cancellation is best-effort and
    does not affect the verdict; the read-back does, because reconciliation
    reads that same call.
    """
    # The host and port are operator-supplied flags, so this script can be aimed
    # at a live gateway. Submitting there would move real money. Refuse.
    non_paper = [account for account in managed_accounts if not is_ibkr_paper_account_id(account)]
    if non_paper or not managed_accounts:
        raise RuntimeError(
            "Refusing --paper-order-check: this session is not a paper session "
            f"({', '.join(managed_accounts) if managed_accounts else 'no account reported'}). "
            f"Only {IBKR_PAPER_ACCOUNT_PREFIX!r} accounts may be used."
        )

    normalized_symbol = symbol.strip().upper()
    print(f"\npaper order        : {side.upper()} {qty:g} {normalized_symbol} @ {limit_price:.2f} LMT DAY", file=out)

    submitted = adapter.place_order(
        OrderRequest(
            account_id=0,
            ticker=normalized_symbol,
            side=side,
            qty=qty,
            price=limit_price,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
        )
    )
    broker_order_id = str(submitted.broker_order_id or "")
    if not broker_order_id:
        raise RuntimeError("Paper order was submitted but IBKR returned no broker order id.")
    print(f"  submitted        : id {broker_order_id} status {submitted.status.value}", file=out)

    observed: BrokerOrder | None = None
    for attempt in range(_ORDER_VISIBILITY_POLL_ATTEMPTS):
        observed = _find_trade(adapter.get_open_trades(), broker_order_id)
        if observed is not None:
            break
        if attempt + 1 < _ORDER_VISIBILITY_POLL_ATTEMPTS:
            time.sleep(_ORDER_VISIBILITY_POLL_DELAY_SECONDS)

    if observed is None:
        # This is the failure that matters: reconciliation reads the same call,
        # so an order it cannot see is an order whose fills would be stranded.
        print(
            f"  FAIL read back   : get_open_trades() never reported id {broker_order_id}",
            file=out,
        )
    else:
        print(
            f"  read back        : status {observed.status.value} "
            f"filled {observed.filled_qty:g}/{observed.qty:g}"
            + (f" reason {observed.status_reason}" if observed.status_reason else ""),
            file=out,
        )

    read_back_ok = observed is not None

    if not cancel:
        print("  cancel           : skipped — the order rests until the close", file=out)
        return read_back_ok

    status = observed.status if observed is not None else submitted.status
    if status not in _CANCELLABLE_STATUSES:
        print(f"  cancel           : skipped — status {status.value} is already terminal", file=out)
        return read_back_ok

    try:
        adapter.cancel_order(broker_order_id)
    except Exception as exc:
        # Best-effort by design: outside market hours IBKR may hold an order
        # pre-submission where a cancel is rejected.
        print(f"  cancel           : best-effort failed ({type(exc).__name__}: {exc})", file=out)
        return read_back_ok

    time.sleep(_ORDER_VISIBILITY_POLL_DELAY_SECONDS)
    after_cancel = _find_trade(adapter.get_open_trades(), broker_order_id)
    if after_cancel is None:
        print("  cancel           : requested; order no longer open", file=out)
    else:
        print(f"  cancel           : requested; status now {after_cancel.status.value}", file=out)
    return read_back_ok


def _require_paper_session(managed_accounts: list[str], *, flag: str) -> None:
    non_paper = [account for account in managed_accounts if not is_ibkr_paper_account_id(account)]
    if non_paper or not managed_accounts:
        raise RuntimeError(
            f"Refusing {flag}: this session is not a paper session "
            f"({', '.join(managed_accounts) if managed_accounts else 'no account reported'}). "
            f"Only {IBKR_PAPER_ACCOUNT_PREFIX!r} accounts may be used."
        )


def _describe_order(order: BrokerOrder) -> str:
    average = f" avg {order.avg_fill_price:g}" if order.avg_fill_price else ""
    reason = f" reason {order.status_reason}" if order.status_reason else ""
    return f"status {order.status.value} filled {order.filled_qty:g}/{order.qty:g}{average}{reason}"


def _submit_market_order(
    adapter: IbkrSocketAdapter, *, out: TextIO, symbol: str, side: str, qty: float, wait_seconds: float
) -> tuple[str, BrokerOrder | None]:
    """Place the market order and poll until it is terminal or the wait ends; return (id, last view)."""
    normalized_symbol = symbol.strip().upper()
    print(f"\nfill lookup check  : {side.upper()} {qty:g} {normalized_symbol} MKT DAY", file=out)
    submitted = adapter.place_order(
        OrderRequest(
            account_id=0,
            ticker=normalized_symbol,
            side=side,
            qty=qty,
            price=0.0,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )
    )
    broker_order_id = str(submitted.broker_order_id or "")
    if not broker_order_id:
        raise RuntimeError("Fill-lookup order was submitted but IBKR returned no broker order id.")
    print(f"  submitted        : id {broker_order_id} status {submitted.status.value}", file=out)

    deadline = time.monotonic() + wait_seconds
    observed = _find_trade(adapter.get_open_trades(), broker_order_id)
    while (observed is None or observed.status not in _TERMINAL_STATUSES) and time.monotonic() < deadline:
        time.sleep(_FILL_POLL_INTERVAL_SECONDS)
        observed = _find_trade(adapter.get_open_trades(), broker_order_id)
    return broker_order_id, observed


def _report_unfilled(
    adapter: IbkrSocketAdapter, broker_order_id: str, observed: BrokerOrder | None, *, out: TextIO, wait_seconds: float
) -> str:
    """Report an order that did not fill; return "fail" if IBKR ended it, else "inconclusive"."""
    detail = _describe_order(observed) if observed is not None else "never reported by get_open_trades()"
    print(f"  first connection : {detail}", file=out)
    if observed is not None and observed.status in _TERMINAL_STATUSES:
        print(
            "  FAIL             : IBKR refused or cancelled the order. "
            "If the size was fractional, the socket path may not accept it.",
            file=out,
        )
        return "fail"
    try:
        adapter.cancel_order(broker_order_id)
        print("  cancel           : requested", file=out)
    except Exception as exc:
        print(f"  cancel           : best-effort failed ({type(exc).__name__}: {exc})", file=out)
    print(f"  INCONCLUSIVE     : no fill within {wait_seconds:g} s. Run this while the market is open.", file=out)
    return "inconclusive"


def _judge_lookup(looked_up: BrokerOrder | None, *, out: TextIO) -> str:
    """Print what get_order rebuilt after the reconnect and return "pass" or "fail"."""
    if looked_up is None:
        print("  FAIL get_order   : returned None for an order that filled on the first connection", file=out)
        return "fail"
    print(f"  get_order        : {_describe_order(looked_up)}", file=out)
    for index, fill in enumerate(looked_up.fills, start=1):
        print(f"  fill {index}           : {fill.filled_qty:g} @ {fill.fill_price:g} exec {fill.exec_id}", file=out)
    filled_from_fills = sum(fill.filled_qty for fill in looked_up.fills)
    print(f"  fills sum        : {filled_from_fills:g}", file=out)
    if len(looked_up.fills) > 1:
        print(
            "  note             : the fill arrived in parts; compare each price with IBKR's statement "
            "(the average above is not any one fill's price)",
            file=out,
        )
    if looked_up.status != OrderStatus.FILLED:
        print(f"  FAIL get_order   : status {looked_up.status.value}, expected filled", file=out)
        return "fail"
    if abs(filled_from_fills - looked_up.filled_qty) > _FILL_SUM_TOLERANCE or not looked_up.fills:
        print("  FAIL get_order   : the fills do not add up to the filled quantity", file=out)
        return "fail"
    return "pass"


def run_fill_lookup_check(
    adapter: IbkrSocketAdapter,
    *,
    reconnect: Callable[[], IbkrSocketAdapter],
    out: TextIO,
    symbol: str,
    side: str,
    qty: float,
    wait_seconds: float,
    managed_accounts: list[str],
) -> str:
    """Fill a market order, reconnect, and look it up by id. Returns "pass", "fail" or "inconclusive".

    "inconclusive" means the order did not fill in time (the market is probably closed), so
    nothing about the lookup was learned; the order is cancelled on a best-effort basis.
    """
    _require_paper_session(managed_accounts, flag="--fill-lookup-check")
    broker_order_id, observed = _submit_market_order(
        adapter, out=out, symbol=symbol, side=side, qty=qty, wait_seconds=wait_seconds
    )
    if observed is None or observed.status != OrderStatus.FILLED:
        return _report_unfilled(adapter, broker_order_id, observed, out=out, wait_seconds=wait_seconds)
    print(f"  first connection : {_describe_order(observed)}", file=out)

    adapter.disconnect()
    print("  reconnecting     : new connection, same client id", file=out)
    second = reconnect()
    try:
        listed = _find_trade(second.get_open_trades(), broker_order_id) is not None
        print(f"  open trades      : id {broker_order_id} {'listed' if listed else 'omitted'}", file=out)
        looked_up = second.get_order(broker_order_id)
    finally:
        second.disconnect()
    return _judge_lookup(looked_up, out=out)


def _report_verdict(args: argparse.Namespace, out: TextIO, *, round_trip_ok: bool, fill_lookup_result: str) -> int:
    if not round_trip_ok:
        # An order the adapter cannot read back is an order whose fills would be
        # stranded by reconciliation. Reporting PASS here would hand an operator
        # a green light for the one thing this check exists to disprove.
        print("\nFAIL: socket path reachable, but the order round trip could not be verified.", file=out)
        return 1

    if fill_lookup_result == "fail":
        print("\nFAIL: the order filled or was refused, but get_order() could not rebuild it.", file=out)
        return 1
    if fill_lookup_result == "inconclusive":
        print("\nINCONCLUSIVE: the order did not fill, so get_order() was not exercised.", file=out)
        return 1

    summary = (
        "reachable, reads succeeded"
        + (", order round trip exercised" if args.paper_order_check else "")
        + (", fill lookup after reconnect verified" if args.fill_lookup_check else "")
    )
    print(f"\nPASS: socket path {summary}.", file=out)
    return 0


def run_smoke_test(args: argparse.Namespace, out: TextIO = sys.stdout) -> int:
    backend = resolve_ibkr_socket_client_backend()
    print(f"backend            : {backend}", file=out)
    print(f"target             : {args.host}:{args.port} client_id={args.client_id}", file=out)

    # True unless --paper-order-check runs and cannot read its order back.
    round_trip_ok = True
    fill_lookup_result = "pass"
    adapter = build_adapter(args.host, args.port, args.client_id)
    try:
        adapter.connect()
    except Exception as exc:
        print(f"FAIL connect       : {type(exc).__name__}: {exc}", file=out)
        print("Is TWS/IB Gateway running with the API enabled on this port?", file=out)
        return 1

    try:
        print("connect            : ok", file=out)

        # This is exactly what `interactive_brokers_socket_paper` asserts on, so
        # report the verdict here — it previews the guard without touching the DB.
        managed_accounts = adapter.managed_accounts()
        print(
            f"managed accounts   : {', '.join(managed_accounts) if managed_accounts else '<none reported>'}", file=out
        )
        print(f"paper venue        : {_paper_venue_verdict(managed_accounts)}", file=out)

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

        if args.paper_order_check:
            round_trip_ok = run_paper_order_check(
                adapter,
                out=out,
                symbol=args.paper_order_symbol,
                side=str(args.paper_order_side).strip().lower(),
                qty=float(args.paper_order_qty),
                limit_price=float(args.paper_order_limit_price),
                cancel=not bool(args.skip_paper_order_cancel),
                managed_accounts=managed_accounts,
            )

        if args.fill_lookup_check:
            fill_lookup_result = run_fill_lookup_check(
                adapter,
                reconnect=lambda: _reconnect(args),
                out=out,
                symbol=args.fill_order_symbol,
                side=str(args.fill_order_side).strip().lower(),
                qty=float(args.fill_order_qty),
                wait_seconds=float(args.fill_wait_seconds),
                managed_accounts=managed_accounts,
            )
    except Exception as exc:
        print(f"FAIL read          : {type(exc).__name__}: {exc}", file=out)
        return 1
    finally:
        adapter.disconnect()
        print("disconnect         : ok", file=out)

    return _report_verdict(args, out, round_trip_ok=round_trip_ok, fill_lookup_result=fill_lookup_result)


def _reconnect(args: argparse.Namespace) -> IbkrSocketAdapter:
    adapter = build_adapter(args.host, args.port, args.client_id)
    adapter.connect()
    return adapter


def main() -> int:
    args = parse_args()
    try:
        validate_paper_order_args(args)
        validate_fill_lookup_args(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return run_smoke_test(args)


if __name__ == "__main__":
    raise SystemExit(main())
