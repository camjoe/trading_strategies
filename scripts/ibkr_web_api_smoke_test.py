"""Manual smoke test for the IBKR Client Portal / Web API integration.

This script is intentionally operator-run only. It uses the existing
InteractiveBrokersWebClient with private configuration loaded from env vars or
an external config file referenced by TRADING_IBKR_WEB_API_CONFIG.

It performs a read-only smoke test:
- session/auth/account validation via client.connect()
- ledger fetch
- summary fetch
- positions fetch

Optionally, it can also run a paper-order lifecycle check behind explicit flags.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Mapping
from typing import TextIO

import httpx

from common.coercion import coerce_float
from infrastructure.brokers.ib_web import InteractiveBrokersWebClient, load_ib_web_api_settings
from infrastructure.brokers.ib_web_adapter import InteractiveBrokersWebAdapter
from trading.models.orders.broker_order import BrokerOrder, OrderStatus, OrderType, TimeInForce

# Default quantity for the optional paper-order smoke check.
_DEFAULT_PAPER_ORDER_QTY = 1.0

# Default side for the optional paper-order smoke check.
_DEFAULT_PAPER_ORDER_SIDE = "buy"

# Only these statuses should trigger a follow-up cancel request in the paper-order check.
_CANCELLABLE_PAPER_ORDER_STATUSES = frozenset(
    {
        OrderStatus.PENDING,
        OrderStatus.SUBMITTED,
        OrderStatus.ACCEPTED,
        OrderStatus.PARTIALLY_FILLED,
    }
)

# Poll live orders a small number of times so a newly submitted paper order has a
# chance to appear without violating IBKR's 1 request / 5 seconds pacing limit.
_ORDER_VISIBILITY_POLL_ATTEMPTS = 2

# IBKR documents GET /iserver/account/orders at 1 request every 5 seconds.
_ORDER_VISIBILITY_POLL_DELAY_SECONDS = 5.0

# Recent-trade verification only needs the current trading day during smoke tests.
_TRADE_LOOKBACK_DAYS = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a read-only IBKR Web API smoke test against the local Client Portal Gateway.",
    )
    parser.add_argument(
        "--paper-order-check",
        action="store_true",
        help="Also run a paper-order lifecycle check with an explicit test limit order.",
    )
    parser.add_argument(
        "--paper-order-symbol",
        default="",
        metavar="SYMBOL",
        help="Ticker symbol for the optional paper-order check.",
    )
    parser.add_argument(
        "--paper-order-qty",
        type=float,
        default=_DEFAULT_PAPER_ORDER_QTY,
        help=f"Quantity for the optional paper-order check (default: {_DEFAULT_PAPER_ORDER_QTY:g}).",
    )
    parser.add_argument(
        "--paper-order-limit-price",
        type=float,
        default=None,
        metavar="PRICE",
        help="Limit price for the optional paper-order check. Use a clearly non-marketable value.",
    )
    parser.add_argument(
        "--paper-order-side",
        choices=("buy", "sell"),
        default=_DEFAULT_PAPER_ORDER_SIDE,
        help=f"Side for the optional paper-order check (default: {_DEFAULT_PAPER_ORDER_SIDE}).",
    )
    parser.add_argument(
        "--skip-paper-order-cancel",
        action="store_true",
        help="Leave the paper test order open instead of requesting cancellation.",
    )
    return parser.parse_args()


def _mask_account_id(account_id: str) -> str:
    value = account_id.strip()
    if not value:
        return "<missing>"
    if len(value) <= 4:
        return "*" * len(value)
    prefix = value[:2]
    suffix = value[-2:]
    return f"{prefix}{'*' * max(0, len(value) - len(prefix) - len(suffix))}{suffix}"


def _redact(text: str, account_id: str) -> str:
    return text.replace(account_id, _mask_account_id(account_id)) if account_id else text


def _extract_amount(payload: Mapping[str, object], key: str) -> str | None:
    raw = payload.get(key)
    if isinstance(raw, Mapping):
        raw = raw.get("amount")
    amount = coerce_float(raw)
    if amount is None:
        return None
    return f"{amount:,.2f}"


def _print_metric(out: TextIO, label: str, value: str | None) -> None:
    if value is not None:
        print(f"  {label}: {value}", file=out)


def _status_label(value: OrderStatus | str | None) -> str:
    if isinstance(value, OrderStatus):
        return value.value
    text = str(value or "").strip()
    return text or "<unknown>"


def _validate_paper_order_args(args: argparse.Namespace) -> None:
    if not args.paper_order_check:
        return
    if not str(args.paper_order_symbol).strip():
        raise ValueError("--paper-order-symbol is required when --paper-order-check is set.")
    if args.paper_order_qty is None or float(args.paper_order_qty) <= 0:
        raise ValueError("--paper-order-qty must be a positive number.")
    if args.paper_order_limit_price is None or float(args.paper_order_limit_price) <= 0:
        raise ValueError("--paper-order-limit-price must be a positive number when --paper-order-check is set.")


def _find_order_status(rows: list[dict[str, object]], broker_order_id: str) -> str | None:
    for row in rows:
        order_id = str(row.get("orderId") or row.get("order_id") or "").strip()
        if order_id == broker_order_id:
            return str(row.get("status") or row.get("order_status") or "").strip() or None
    return None


def _extract_status_text(payload: Mapping[str, object]) -> str | None:
    for key in ("order_status", "status", "order_status_description"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return None


def _find_order_row(rows: list[dict[str, object]], broker_order_id: str) -> dict[str, object] | None:
    for row in rows:
        order_id = str(row.get("orderId") or row.get("order_id") or "").strip()
        if order_id == broker_order_id:
            return row
    return None


def _normalize_status_text(value: str | None) -> str:
    return str(value or "").strip().replace("_", "").replace(" ", "").lower()


def _is_cancellable_lifecycle_status(
    submitted_status: OrderStatus,
    *,
    status_text: str | None,
    order_row_status: str | None,
) -> bool:
    if submitted_status in _CANCELLABLE_PAPER_ORDER_STATUSES:
        return True
    normalized = _normalize_status_text(status_text) or _normalize_status_text(order_row_status)
    return normalized in {
        "pending",
        "pendingsubmit",
        "presubmitted",
        "submitted",
        "accepted",
        "apipending",
        "partiallyfilled",
    }


def _find_matching_trade(
    rows: list[dict[str, object]],
    *,
    symbol: str,
    side: str,
    qty: float,
) -> dict[str, object] | None:
    normalized_symbol = symbol.strip().upper()
    normalized_side = side.strip().upper()
    for row in rows:
        trade_symbol = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
        trade_side = str(row.get("side") or "").strip().upper()
        trade_qty = coerce_float(row.get("size"))
        if trade_symbol != normalized_symbol:
            continue
        if trade_side not in {normalized_side, normalized_side[:1]}:
            continue
        if trade_qty != qty:
            continue
        return row
    return None


def _probe_order_lifecycle(
    *,
    client: InteractiveBrokersWebClient,
    broker_order_id: str,
    symbol: str,
    side: str,
    qty: float,
    out: TextIO,
) -> tuple[str | None, str | None]:
    status_payload = client.fetch_order_status(broker_order_id)
    status_text = _extract_status_text(status_payload)
    if status_text is not None:
        print(f"✓ Order-status lookup returned {status_text}", file=out)

    order_row_status: str | None = None
    order_row: dict[str, object] | None = None
    for attempt in range(_ORDER_VISIBILITY_POLL_ATTEMPTS):
        order_row = _find_order_row(client.fetch_orders(), broker_order_id)
        if order_row is not None:
            order_row_status = str(order_row.get("status") or order_row.get("order_status") or "").strip() or None
            print(
                f"✓ Live-orders lookup returned status {_status_label(order_row_status)}",
                file=out,
            )
            break
        if attempt + 1 < _ORDER_VISIBILITY_POLL_ATTEMPTS:
            time.sleep(_ORDER_VISIBILITY_POLL_DELAY_SECONDS)

    if order_row is None:
        print(
            "✓ Live-orders lookup returned no row after follow-up polling; "
            "the order may still be pending, outside market hours, or not yet visible there.",
            file=out,
        )

    matching_trade = _find_matching_trade(
        client.fetch_trades(days=_TRADE_LOOKBACK_DAYS),
        symbol=symbol,
        side=side,
        qty=qty,
    )
    if matching_trade is not None:
        print(
            "✓ Recent-trades lookup found a matching symbol/side/qty execution "
            f"at {matching_trade.get('trade_time') or matching_trade.get('trade_time_r') or '<unknown time>'}",
            file=out,
        )
    else:
        print("✓ Recent-trades lookup found no matching execution yet.", file=out)

    return status_text, order_row_status


def run_smoke_test(
    client: InteractiveBrokersWebClient,
    *,
    account_id: str,
    out: TextIO,
) -> None:
    masked_account_id = _mask_account_id(account_id)
    client.connect()
    print(f"✓ Session validated for account {masked_account_id}", file=out)

    ledger = client.fetch_ledger()
    summary = client.fetch_summary()
    positions = client.fetch_positions()

    base_ledger = ledger.get("BASE")
    currency_bucket_count = sum(1 for value in ledger.values() if isinstance(value, Mapping))

    print(f"✓ Ledger loaded ({currency_bucket_count} currency bucket(s))", file=out)
    if isinstance(base_ledger, Mapping):
        _print_metric(out, "Cash balance (BASE)", _extract_amount(base_ledger, "cashbalance"))
        _print_metric(
            out,
            "Net liquidation (BASE)",
            _extract_amount(base_ledger, "netliquidationvalue"),
        )

    print("✓ Summary loaded", file=out)
    _print_metric(out, "Buying power", _extract_amount(summary, "buyingpower"))
    _print_metric(out, "Net liquidation", _extract_amount(summary, "netliquidation"))

    print(f"✓ Positions loaded ({len(positions)} row(s))", file=out)


def run_paper_order_check(
    *,
    client: InteractiveBrokersWebClient,
    adapter: InteractiveBrokersWebAdapter,
    out: TextIO,
    symbol: str,
    qty: float,
    limit_price: float,
    side: str,
    cancel_order: bool,
) -> None:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("Paper-order smoke test requires a ticker symbol.")

    submitted = adapter.place_order(
        BrokerOrder(
            account_id=0,
            ticker=normalized_symbol,
            side=side,
            qty=qty,
            price=limit_price,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
        )
    )
    if not submitted.broker_order_id:
        raise RuntimeError("Paper-order smoke test did not receive a broker order id.")

    print(
        "✓ Paper order submitted: "
        f"{side.upper()} {qty:g} {normalized_symbol} @ {limit_price:.2f} "
        f"(id {submitted.broker_order_id}, status {_status_label(submitted.status)})",
        file=out,
    )
    status_text, order_row_status = _probe_order_lifecycle(
        client=client,
        broker_order_id=submitted.broker_order_id,
        symbol=normalized_symbol,
        side=side,
        qty=qty,
        out=out,
    )

    if not cancel_order:
        print("✓ Left the paper test order open because --skip-paper-order-cancel was set.", file=out)
        return
    if not _is_cancellable_lifecycle_status(
        submitted.status,
        status_text=status_text,
        order_row_status=order_row_status,
    ):
        print(
            "✓ Skipped cancel because broker lifecycle status is "
            f"{_status_label(status_text or order_row_status or submitted.status)}.",
            file=out,
        )
        return

    adapter.cancel_order(submitted.broker_order_id)
    print(f"✓ Cancel request submitted for order {submitted.broker_order_id}", file=out)

    status_after_cancel = _extract_status_text(client.fetch_order_status(submitted.broker_order_id))
    if status_after_cancel is not None:
        print(f"  Broker-reported post-cancel status: {status_after_cancel}", file=out)


def main() -> int:
    args = parse_args()
    _validate_paper_order_args(args)
    settings = None
    client = None

    try:
        settings = load_ib_web_api_settings()
        client = InteractiveBrokersWebClient(settings)
        run_smoke_test(client, account_id=settings.account_id, out=sys.stdout)
        if args.paper_order_check:
            run_paper_order_check(
                client=client,
                adapter=InteractiveBrokersWebAdapter(client),
                out=sys.stdout,
                symbol=args.paper_order_symbol,
                qty=float(args.paper_order_qty),
                limit_price=float(args.paper_order_limit_price),
                side=str(args.paper_order_side).strip().lower(),
                cancel_order=not bool(args.skip_paper_order_cancel),
            )
    except (RuntimeError, ValueError, httpx.HTTPError) as exc:
        message = str(exc)
        if settings is not None:
            message = _redact(message, settings.account_id)
        print(f"✗ IBKR Web API smoke test failed: {message}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
