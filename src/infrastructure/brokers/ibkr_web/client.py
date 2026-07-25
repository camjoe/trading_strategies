"""IBKR Client Portal / Web API HTTP client.

The Web API path is kept separate from the existing TWS / Gateway socket client.
All HTTP transport details, session handling, and account identifier lookup stay
inside ``brokers/`` so higher layers continue to depend only on ``BrokerConnection``.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import httpx

from common.coercion import coerce_str
from infrastructure.brokers.ibkr_web.pacing import (
    _DEFAULT_IB_WEB_API_PACING_LIMITER,
    IbWebApiPacingLimiter,
)
from infrastructure.brokers.ibkr_web.settings import IbWebApiSettings

# Session reply confirmations are interactive notices; cap automated confirms.
_MAX_ORDER_REPLY_CONFIRMATIONS = 5

# Market-data field tags for last, bid, and ask in snapshot responses.
_MARKETDATA_SNAPSHOT_FIELDS = "31,84,86"

# The first page of the portfolio positions endpoint.
_POSITIONS_PAGE = 0


@dataclass(frozen=True)
class IbWebApiContract:
    """Resolved IBKR contract details required for order placement."""

    conid: str
    ticker: str
    sec_type: str
    listing_exchange: str


class IbWebOrderStatusUnavailableError(RuntimeError):
    """Raised when IBKR no longer has a completed order in its status cache."""


class InteractiveBrokersWebClient:
    """Thin HTTP client for the IBKR Client Portal / Web API."""

    def __init__(
        self,
        settings: IbWebApiSettings,
        http_client: httpx.Client | None = None,
        pacing_limiter: IbWebApiPacingLimiter | None = None,
    ) -> None:
        self._settings = settings
        self._client = http_client or httpx.Client(
            base_url=settings.base_url,
            headers=settings.headers,
            timeout=settings.timeout_seconds,
            verify=settings.verify_ssl,
        )
        self._owns_client = http_client is None
        self._pacing_limiter = pacing_limiter or _DEFAULT_IB_WEB_API_PACING_LIMITER
        self._connected = False
        self._conid_cache: dict[str, str] = {}
        self._contract_cache: dict[str, IbWebApiContract] = {}
        self._keepalive_stop_event = threading.Event()
        self._keepalive_thread: threading.Thread | None = None
        self._background_error: RuntimeError | None = None

    @property
    def account_id(self) -> str:
        return self._settings.account_id

    def connect(self) -> None:
        self.validate_session()
        self._connected = True
        self._background_error = None
        self._start_keepalive_if_enabled()

    def disconnect(self) -> None:
        self._stop_keepalive()
        if self._owns_client:
            self._client.close()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def validate_session(self) -> None:
        status = self.fetch_auth_status()
        if not _truthy_flag(status.get("authenticated")):
            raise RuntimeError("IBKR Web API session is not authenticated.")
        if not _truthy_flag(status.get("connected")):
            raise RuntimeError("IBKR Web API session is not connected to brokerage infrastructure.")

        portfolio_account_ids = self.fetch_portfolio_account_ids()
        if self._settings.account_id not in portfolio_account_ids:
            raise RuntimeError(
                f"Configured IBKR Web API account_id {self._settings.account_id!r} "
                "is not visible in the current session."
            )

        trade_account_ids = self.fetch_trade_account_ids()
        if trade_account_ids and self._settings.account_id not in trade_account_ids:
            raise RuntimeError(
                f"Configured IBKR Web API account_id {self._settings.account_id!r} "
                "is not enabled for trading in the current session."
            )

    def fetch_auth_status(self) -> dict[str, object]:
        payload = self._request_json("GET", "/iserver/auth/status")
        if not isinstance(payload, dict):
            raise RuntimeError("IBKR Web API auth status response must be an object.")
        return payload

    def fetch_portfolio_account_ids(self) -> list[str]:
        payload = self._request_json("GET", "/portfolio/accounts")
        if not isinstance(payload, list):
            raise RuntimeError("IBKR Web API portfolio accounts response must be a list.")
        account_ids: list[str] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            for key in ("accountId", "id", "displayName", "desc"):
                value = coerce_str(item.get(key))
                if value:
                    account_ids.append(value)
                    break
        return account_ids

    def fetch_trade_account_ids(self) -> list[str]:
        payload = self._request_json("GET", "/iserver/accounts")
        if isinstance(payload, dict):
            values = payload.get("accounts", [])
            if isinstance(values, list):
                return [str(value) for value in values if str(value).strip()]
        if isinstance(payload, list):
            return [str(value) for value in payload if str(value).strip()]
        return []

    def fetch_trade_accounts(self) -> dict[str, object]:
        payload = self._request_json("GET", "/iserver/accounts")
        if not isinstance(payload, dict):
            raise RuntimeError("IBKR Web API trading accounts response must be an object.")
        return payload

    def tickle(self) -> dict[str, object]:
        payload = self._request_json("GET", "/tickle")
        if not isinstance(payload, dict):
            raise RuntimeError("IBKR Web API tickle response must be an object.")
        return payload

    def fetch_ledger(self) -> dict[str, object]:
        payload = self._request_json("GET", f"/portfolio/{self._settings.account_id}/ledger")
        if not isinstance(payload, dict):
            raise RuntimeError("IBKR Web API ledger response must be an object.")
        return payload

    def fetch_summary(self) -> dict[str, object]:
        payload = self._request_json("GET", f"/portfolio/{self._settings.account_id}/summary")
        if not isinstance(payload, dict):
            raise RuntimeError("IBKR Web API summary response must be an object.")
        return payload

    def fetch_positions(self) -> list[dict[str, object]]:
        payload = self._request_json(
            "GET",
            f"/portfolio/{self._settings.account_id}/positions/{_POSITIONS_PAGE}",
        )
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            rows = payload.get("positions")
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
        raise RuntimeError("IBKR Web API positions response must be a list or an object with positions.")

    def fetch_orders(self) -> list[dict[str, object]]:
        payload = self._request_json(
            "GET",
            "/iserver/account/orders",
            params={"accountId": self._settings.account_id, "force": "true"},
        )
        if isinstance(payload, dict):
            orders = payload.get("orders")
            if isinstance(orders, list):
                return [item for item in orders if isinstance(item, dict)]
        raise RuntimeError("IBKR Web API account orders response must contain an orders list.")

    def fetch_order_status(self, order_id: str) -> dict[str, object]:
        try:
            payload = self._request_json("GET", f"/iserver/account/order/status/{order_id}")
        except RuntimeError as exc:
            cause = exc.__cause__
            if isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code == 503:
                raise IbWebOrderStatusUnavailableError(str(exc)) from exc
            raise
        if not isinstance(payload, dict):
            raise RuntimeError("IBKR Web API order status response must be an object.")
        return payload

    def fetch_trades(self, *, days: int = 1) -> list[dict[str, object]]:
        payload = self._request_json(
            "GET",
            "/iserver/account/trades",
            params={"days": str(days)},
        )
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        raise RuntimeError("IBKR Web API trades response must be a list.")

    def resolve_conid(self, symbol: str) -> str:
        return self.resolve_contract(symbol).conid

    def resolve_contract(self, symbol: str) -> IbWebApiContract:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("Ticker symbol is required for IBKR Web API conid lookup.")
        cached = self._contract_cache.get(normalized)
        if cached:
            return cached

        payload = self._request_json(
            "GET",
            "/iserver/secdef/search",
            params={"symbol": normalized, "secType": "STK"},
        )
        if not isinstance(payload, list):
            raise RuntimeError("IBKR Web API contract search response must be a list.")

        fallback_conid: str | None = None
        for item in payload:
            if not isinstance(item, dict):
                continue
            conid = coerce_str(item.get("conid"))
            if not conid:
                continue
            if fallback_conid is None:
                fallback_conid = conid
            resolved_symbol = (coerce_str(item.get("symbol")) or coerce_str(item.get("ticker")) or "").upper()
            if resolved_symbol == normalized:
                return self._load_contract_details(normalized, conid)

        if fallback_conid is None:
            raise RuntimeError(f"IBKR Web API could not resolve a contract id for ticker {normalized!r}.")

        return self._load_contract_details(normalized, fallback_conid)

    def fetch_marketdata_snapshot(self, conids: list[str]) -> list[dict[str, object]]:
        csv = ",".join(conids)
        first = self._request_json(
            "GET",
            "/iserver/marketdata/snapshot",
            params={"conids": csv, "fields": _MARKETDATA_SNAPSHOT_FIELDS},
        )
        if not isinstance(first, list):
            raise RuntimeError("IBKR Web API marketdata snapshot response must be a list.")
        rows = [item for item in first if isinstance(item, dict)]
        if _is_marketdata_preflight_only(rows):
            second = self._request_json("GET", "/iserver/marketdata/snapshot", params={"conids": csv})
            if not isinstance(second, list):
                raise RuntimeError("IBKR Web API marketdata snapshot follow-up response must be a list.")
            return [item for item in second if isinstance(item, dict)]
        return rows

    def submit_order(self, ticket: dict[str, object]) -> dict[str, object]:
        payload = self._request_json(
            "POST",
            f"/iserver/account/{self._settings.account_id}/orders",
            json={"orders": [ticket]},
        )
        confirmations = 0
        while _is_order_reply_message(payload):
            message_id = str(payload[0]["id"])
            payload = self._request_json(
                "POST",
                f"/iserver/reply/{message_id}",
                json={"confirmed": True},
            )
            confirmations += 1
            if confirmations > _MAX_ORDER_REPLY_CONFIRMATIONS:
                raise RuntimeError("IBKR Web API order reply confirmation loop exceeded safety limit.")

        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            payload = payload[0]
        if isinstance(payload, dict) and "error" in payload:
            raise RuntimeError(str(payload["error"]))
        if not isinstance(payload, dict) or "order_id" not in payload:
            raise RuntimeError("IBKR Web API order submission did not return an acknowledgement.")
        return payload

    def _load_contract_details(self, symbol: str, conid: str) -> IbWebApiContract:
        payload = self._request_json("GET", "/trsrv/secdef", params={"conids": conid})
        if not isinstance(payload, dict):
            raise RuntimeError("IBKR Web API security definition response must be an object.")
        rows = payload.get("secdef")
        if not isinstance(rows, list):
            raise RuntimeError("IBKR Web API security definition response must contain a secdef list.")

        for item in rows:
            if not isinstance(item, dict):
                continue
            if coerce_str(item.get("conid")) != conid:
                continue
            contract = IbWebApiContract(
                conid=conid,
                ticker=(coerce_str(item.get("ticker")) or symbol).upper(),
                sec_type=(coerce_str(item.get("assetClass")) or "STK").upper(),
                listing_exchange=coerce_str(item.get("listingExchange")) or "SMART",
            )
            self._conid_cache[symbol] = conid
            self._contract_cache[symbol] = contract
            return contract

        raise RuntimeError(f"IBKR Web API could not load security details for conid {conid}.")

    def cancel_order(self, order_id: str) -> dict[str, object]:
        payload = self._request_json(
            "DELETE",
            f"/iserver/account/{self._settings.account_id}/order/{order_id}",
        )
        if not isinstance(payload, dict):
            raise RuntimeError("IBKR Web API cancel-order response must be an object.")
        return payload

    def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        self._raise_if_background_error()
        self._pacing_limiter.wait_for_slot(method, path)
        response = self._client.request(method, path, **kwargs)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip()
            if response.status_code == 429:
                raise RuntimeError(
                    f"IBKR Web API pacing limit exceeded for {method} {path}: {response.status_code} {detail}"
                ) from exc
            raise RuntimeError(
                f"IBKR Web API request failed for {method} {path}: {response.status_code} {detail}"
            ) from exc
        if not response.content:
            return {}
        return response.json()

    def _start_keepalive_if_enabled(self) -> None:
        if not self._settings.keepalive_enabled:
            return
        if self._keepalive_thread is not None and self._keepalive_thread.is_alive():
            return
        self._keepalive_stop_event.clear()
        self._keepalive_thread = threading.Thread(
            target=self._run_keepalive_loop,
            name="ibkr-web-keepalive",
            daemon=True,
        )
        self._keepalive_thread.start()

    def _stop_keepalive(self) -> None:
        self._keepalive_stop_event.set()
        thread = self._keepalive_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        self._keepalive_thread = None

    def _run_keepalive_loop(self) -> None:
        while not self._keepalive_stop_event.wait(self._settings.keepalive_interval_seconds):
            if not self._connected:
                return
            try:
                self.tickle()
            except RuntimeError as exc:
                self._background_error = RuntimeError(f"IBKR Web API keepalive failed: {exc}")
                self._connected = False
                return

    def _raise_if_background_error(self) -> None:
        if self._background_error is not None:
            raise self._background_error


def _truthy_flag(value: object | None) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _is_marketdata_preflight_only(rows: list[dict[str, object]]) -> bool:
    if not rows:
        return False
    for row in rows:
        if any(field in row for field in ("31", "84", "86")):
            return False
    return True


def _is_order_reply_message(payload: object) -> bool:
    if not isinstance(payload, list) or not payload:
        return False
    return all(isinstance(item, dict) and "id" in item for item in payload)
