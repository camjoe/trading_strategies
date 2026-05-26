"""Interactive Brokers Web API adapter.

Uses the Client Portal / Campus Web API through ``InteractiveBrokersWebClient``.
Account identifiers and session headers are loaded from env or ignored local
config via ``load_ib_web_api_settings`` — they are not stored in the app DB.
"""

from __future__ import annotations

import time

from common.time import utc_now_iso
from trading.brokers.base import BrokerConnection, BrokerOrder, OrderFill, OrderStatus, OrderType
from trading.brokers.ib_web_client import InteractiveBrokersWebClient
from common.coercion import coerce_bool, coerce_float

# Account summary fields expected by the service layer.
_ACCOUNT_INFO_FIELDS = (
    "TotalCashValue",
    "BuyingPower",
    "GrossPositionValue",
    "NetLiquidation",
)

# IBKR requires a unique customer order id for each order within a 24-hour span.
_WEB_ORDER_ID_PREFIX = "ts-web"


class InteractiveBrokersWebAdapter(BrokerConnection):
    """Live broker adapter backed by the IBKR Web API."""

    def __init__(self, client: InteractiveBrokersWebClient) -> None:
        self._client = client

    def connect(self) -> None:
        self._client.connect()

    def disconnect(self) -> None:
        self._client.disconnect()

    def place_order(self, order: BrokerOrder) -> BrokerOrder:
        self._require_connected()
        contract = self._client.resolve_contract(order.ticker)
        trading_accounts = self._client.fetch_trade_accounts()
        payload: dict[str, object] = {
            "acctId": self._client.account_id,
            "conid": int(contract.conid),
            "secType": f"{contract.conid}:{contract.sec_type}",
            "cOID": _build_customer_order_id(order),
            "listingExchange": contract.listing_exchange,
            "side": order.side.upper(),
            "orderType": "MKT" if order.order_type == OrderType.MARKET else "LMT",
            "ticker": contract.ticker,
            "tif": order.time_in_force.value.upper(),
            "quantity": order.qty,
        }
        if _requires_manual_order_time(trading_accounts, self._client.account_id):
            payload["manualOrderTime"] = int(time.time())
        if order.order_type == OrderType.LIMIT:
            payload["price"] = order.price

        response = self._client.submit_order(payload)
        now = utc_now_iso()
        order.broker_order_id = str(response["order_id"])
        order.status = _map_ib_web_status(str(response.get("order_status", "Submitted")))
        order.submitted_at = now
        order.updated_at = now
        return order

    def cancel_order(self, broker_order_id: str) -> None:
        self._require_connected()
        self._client.cancel_order(broker_order_id)

    def get_open_trades(self) -> list[BrokerOrder]:
        self._require_connected()
        result: list[BrokerOrder] = []
        for row in self._client.fetch_orders():
            broker_order_id = str(row.get("orderId") or row.get("order_id") or "").strip()
            if not broker_order_id:
                continue
            ticker = str(row.get("ticker") or row.get("description1") or "").strip()
            if not ticker:
                continue

            qty = _coerce_number(row.get("totalSize") or row.get("quantity")) or 0.0
            filled_qty = _coerce_number(row.get("filledQuantity")) or 0.0
            avg_fill_price = _coerce_number(row.get("avgPrice"))
            order_status = _map_ib_web_status(str(row.get("status") or row.get("order_status") or "Submitted"))
            if order_status == OrderStatus.SUBMITTED and 0.0 < filled_qty < qty:
                order_status = OrderStatus.PARTIALLY_FILLED

            fills: list[OrderFill] = []
            fill_time = _normalize_fill_time(row.get("lastExecutionTime") or row.get("lastExecutionTime_r"))
            if filled_qty > 0 and avg_fill_price is not None:
                fills.append(
                    OrderFill(
                        filled_qty=filled_qty,
                        fill_price=avg_fill_price,
                        fill_time=fill_time,
                        commission=_coerce_number(row.get("commission")) or 0.0,
                        exec_id=f"web-{broker_order_id}-{filled_qty}-{fill_time}",
                    )
                )

            result.append(
                BrokerOrder(
                    account_id=0,
                    ticker=ticker,
                    side=str(row.get("side") or "").strip().lower(),
                    qty=qty,
                    price=_coerce_number(row.get("price") or row.get("limitPrice")) or 0.0,
                    broker_order_id=broker_order_id,
                    status=order_status,
                    filled_qty=filled_qty,
                    avg_fill_price=avg_fill_price,
                    commission=_coerce_number(row.get("commission")) or 0.0,
                    fills=fills,
                )
            )
        return result

    def get_positions(self) -> dict[str, float]:
        self._require_connected()
        positions: dict[str, float] = {}
        for row in self._client.fetch_positions():
            ticker = str(row.get("ticker") or row.get("contractDesc") or row.get("description") or "").strip()
            if not ticker:
                continue
            quantity = _coerce_number(row.get("position"))
            if quantity is None:
                continue
            positions[ticker] = quantity
        return positions

    def get_account_info(self) -> dict[str, float]:
        self._require_connected()
        ledger = self._client.fetch_ledger()
        summary = self._client.fetch_summary()

        ledger_row = _select_ledger_row(ledger)
        account_info = {
            "TotalCashValue": _coerce_number(ledger_row.get("cashbalance") or ledger_row.get("settledcash")) or 0.0,
            "BuyingPower": (
                _summary_amount(summary, "buyingpower")
                or _summary_amount(summary, "availablefunds")
                or _coerce_number(ledger_row.get("cashbalance"))
                or 0.0
            ),
            "GrossPositionValue": _coerce_number(ledger_row.get("stockmarketvalue")) or 0.0,
            "NetLiquidation": (
                _summary_amount(summary, "netliquidation")
                or _coerce_number(ledger_row.get("netliquidationvalue"))
                or 0.0
            ),
        }
        return {key: float(account_info[key]) for key in _ACCOUNT_INFO_FIELDS}

    def get_quotes(self, tickers: list[str]) -> dict[str, dict[str, float]]:
        self._require_connected()
        conid_to_symbol = {self._client.resolve_conid(ticker): ticker for ticker in tickers}
        rows = self._client.fetch_marketdata_snapshot(list(conid_to_symbol))
        quotes: dict[str, dict[str, float]] = {}
        for row in rows:
            conid = str(row.get("conid") or "").strip()
            symbol = conid_to_symbol.get(conid)
            if symbol is None:
                continue
            quotes[symbol] = {
                "bid": _coerce_number(row.get("84")) or 0.0,
                "ask": _coerce_number(row.get("86")) or 0.0,
                "last": _coerce_number(row.get("31")) or 0.0,
            }
        return quotes

    def _require_connected(self) -> None:
        if not self._client.is_connected():
            raise RuntimeError("InteractiveBrokersWebAdapter is not connected. Call connect() first.")


_IB_WEB_STATUS_MAP: dict[str, OrderStatus] = {
    "pendingsubmit": OrderStatus.PENDING,
    "pendingcancel": OrderStatus.PENDING,
    "presubmitted": OrderStatus.SUBMITTED,
    "submitted": OrderStatus.SUBMITTED,
    "apipending": OrderStatus.SUBMITTED,
    "accepted": OrderStatus.ACCEPTED,
    "cancelled": OrderStatus.CANCELLED,
    "apicancelled": OrderStatus.CANCELLED,
    "filled": OrderStatus.FILLED,
    "partiallyfilled": OrderStatus.PARTIALLY_FILLED,
    "inactive": OrderStatus.REJECTED,
}


def _map_ib_web_status(status: str) -> OrderStatus:
    normalized = status.strip().replace(" ", "").lower()
    return _IB_WEB_STATUS_MAP.get(normalized, OrderStatus.SUBMITTED)


def _coerce_number(value: object | None) -> float | None:
    if value is None:
        return None
    normalized = str(value).strip().replace(",", "")
    if not normalized:
        return None
    return coerce_float(normalized)


def _normalize_fill_time(value: object | None) -> str:
    if value is None:
        return utc_now_iso()
    text = str(value).strip()
    return text or utc_now_iso()


def _select_ledger_row(ledger: dict[str, object]) -> dict[str, object]:
    for key in ("BASE", "USD"):
        row = ledger.get(key)
        if isinstance(row, dict):
            return row
    for row in ledger.values():
        if isinstance(row, dict):
            return row
    return {}


def _summary_amount(summary: dict[str, object], key: str) -> float | None:
    entry = summary.get(key)
    if not isinstance(entry, dict):
        return None
    return _coerce_number(entry.get("amount") or entry.get("value"))


def _requires_manual_order_time(accounts_payload: dict[str, object], account_id: str) -> bool:
    acct_props = accounts_payload.get("acctProps")
    if not isinstance(acct_props, dict):
        return False
    account_props = acct_props.get(account_id)
    if not isinstance(account_props, dict):
        return False
    return _coerce_bool_flag(account_props.get("allowCustomerTime"))


def _build_customer_order_id(order: BrokerOrder) -> str:
    symbol = order.ticker.strip().upper() or "UNKNOWN"
    side = order.side.strip().upper() or "UNKNOWN"
    return f"{_WEB_ORDER_ID_PREFIX}-{symbol}-{side}-{time.time_ns()}"


def _coerce_bool_flag(value: object | None) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        parsed = coerce_bool(text)
    except ValueError:
        return False
    return bool(parsed) if parsed is not None else False
