"""Interactive Brokers Web API client utilities.

The Web API path is kept separate from the existing TWS / Gateway socket client.
All HTTP transport details, session handling, and account identifier lookup stay
inside ``trading/brokers/`` so higher layers continue to depend only on
``BrokerConnection``.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from common.project_paths import LOCAL_DIR
from trading.utils.coercion import coerce_bool, coerce_float, coerce_str

# Default local Client Portal Gateway base URL.
_DEFAULT_WEB_API_BASE_URL = "https://localhost:5000/v1/api"

# Default timeout for individual Web API requests in seconds.
_DEFAULT_TIMEOUT_SECONDS = 10.0

# Default ignored local config file for operator-managed Web API settings.
_DEFAULT_WEB_API_CONFIG_PATH = LOCAL_DIR / "ibkr_web_api_config.json"

# IBKR's documented global Client Portal pacing limit is 10 requests per second.
_GLOBAL_REQUEST_LIMIT = 10

# The global pacing window is one second.
_GLOBAL_REQUEST_WINDOW_SECONDS = 1.0

# Session reply confirmations are interactive notices; cap automated confirms.
_MAX_ORDER_REPLY_CONFIRMATIONS = 5

# Market-data field tags for last, bid, and ask in snapshot responses.
_MARKETDATA_SNAPSHOT_FIELDS = "31,84,86"

# The first page of the portfolio positions endpoint.
_POSITIONS_PAGE = 0

# Endpoint-specific minimum spacing from the IBKR Client Portal pacing table.
_ENDPOINT_MIN_INTERVAL_SECONDS: dict[tuple[str, str], float] = {
    ("GET", "/portfolio/accounts"): 5.0,
    ("GET", "/portfolio/subaccounts"): 5.0,
    ("GET", "/iserver/account/orders"): 5.0,
    ("GET", "/iserver/account/pnl/partitioned"): 5.0,
    ("GET", "/iserver/account/trades"): 5.0,
    ("GET", "/sso/validate"): 60.0,
    ("GET", "/tickle"): 1.0,
}


@dataclass(frozen=True)
class IbWebApiSettings:
    """Operator-managed Web API settings loaded from env or ignored local config."""

    base_url: str
    account_id: str
    headers: dict[str, str]
    verify_ssl: bool = False
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS


class IbWebApiPacingLimiter:
    """Process-local pacing guard for IBKR Client Portal API limits."""

    def __init__(
        self,
        *,
        time_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self._time_fn = time_fn or time.monotonic
        self._sleep_fn = sleep_fn or time.sleep
        self._lock = threading.Lock()
        self._recent_request_times: deque[float] = deque()
        self._endpoint_last_request_times: dict[tuple[str, str], float] = {}

    def wait_for_slot(self, method: str, path: str) -> None:
        endpoint_key = (method.strip().upper(), path)
        while True:
            wait_seconds = 0.0
            with self._lock:
                now = float(self._time_fn())
                self._evict_global_window(now)

                if len(self._recent_request_times) >= _GLOBAL_REQUEST_LIMIT:
                    oldest = self._recent_request_times[0]
                    wait_seconds = max(
                        wait_seconds,
                        oldest + _GLOBAL_REQUEST_WINDOW_SECONDS - now,
                    )

                min_interval = _ENDPOINT_MIN_INTERVAL_SECONDS.get(endpoint_key)
                if min_interval is not None:
                    last_request_at = self._endpoint_last_request_times.get(endpoint_key)
                    if last_request_at is not None:
                        wait_seconds = max(wait_seconds, last_request_at + min_interval - now)

                if wait_seconds <= 0:
                    self._recent_request_times.append(now)
                    if min_interval is not None:
                        self._endpoint_last_request_times[endpoint_key] = now
                    return

            self._sleep_fn(wait_seconds)

    def _evict_global_window(self, now: float) -> None:
        cutoff = now - _GLOBAL_REQUEST_WINDOW_SECONDS
        while self._recent_request_times and self._recent_request_times[0] <= cutoff:
            self._recent_request_times.popleft()


_DEFAULT_IB_WEB_API_PACING_LIMITER = IbWebApiPacingLimiter()


def _config_path() -> Path:
    raw = str(os.getenv("TRADING_IBKR_WEB_API_CONFIG", "")).strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _DEFAULT_WEB_API_CONFIG_PATH


def _file_payload(config_path: Path) -> dict[str, object]:
    if not config_path.exists():
        return {}
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"IBKR Web API config must be a JSON object: {config_path}")
    return payload


def _coerce_headers(value: object | None) -> dict[str, str]:
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("IBKR Web API headers must decode to a JSON object.")
        value = parsed
    if not isinstance(value, Mapping):
        raise ValueError("IBKR Web API headers must be a mapping of header names to values.")
    return {str(key): str(raw_value) for key, raw_value in value.items() if str(raw_value).strip()}


def _config_value(
    env_name: str,
    payload: Mapping[str, object],
    field_name: str,
) -> object | None:
    raw_env = os.getenv(env_name)
    if raw_env is not None and str(raw_env).strip():
        return raw_env
    return payload.get(field_name)


def load_ib_web_api_settings() -> IbWebApiSettings:
    """Load operator-managed Web API settings from env or ignored local config.

    Precedence is env first, then ``local/ibkr_web_api_config.json``.
    Sensitive account IDs and session headers stay outside the tracked repo state.
    """

    payload = _file_payload(_config_path())

    base_url_raw = _config_value("TRADING_IBKR_WEB_API_BASE_URL", payload, "base_url")
    account_id_raw = _config_value("TRADING_IBKR_WEB_API_ACCOUNT_ID", payload, "account_id")
    headers_raw = _config_value("TRADING_IBKR_WEB_API_HEADERS_JSON", payload, "headers")
    session_token_raw = _config_value("TRADING_IBKR_WEB_API_SESSION_TOKEN", payload, "session_token")
    verify_ssl_raw = _config_value("TRADING_IBKR_WEB_API_VERIFY_SSL", payload, "verify_ssl")
    timeout_raw = _config_value("TRADING_IBKR_WEB_API_TIMEOUT_SECONDS", payload, "timeout_seconds")

    base_url = str(base_url_raw or _DEFAULT_WEB_API_BASE_URL).strip().rstrip("/")
    account_id = str(account_id_raw or "").strip()
    if not account_id:
        raise ValueError(
            "IBKR Web API account_id is required. Set TRADING_IBKR_WEB_API_ACCOUNT_ID "
            "or add account_id to local/ibkr_web_api_config.json."
        )

    headers = _coerce_headers(headers_raw)
    session_token = str(session_token_raw or "").strip()
    if session_token and "Cookie" not in headers:
        headers["Cookie"] = f"api={session_token}"

    verify_ssl = base_url != _DEFAULT_WEB_API_BASE_URL
    if verify_ssl_raw is not None:
        coerced_verify = coerce_bool(verify_ssl_raw)
        if coerced_verify is None:
            raise ValueError("IBKR Web API verify_ssl must be a boolean value.")
        verify_ssl = bool(coerced_verify)

    timeout_seconds = _DEFAULT_TIMEOUT_SECONDS
    if timeout_raw is not None:
        coerced_timeout = coerce_float(timeout_raw)
        if coerced_timeout is None or coerced_timeout <= 0:
            raise ValueError("IBKR Web API timeout_seconds must be a positive number.")
        timeout_seconds = float(coerced_timeout)

    return IbWebApiSettings(
        base_url=base_url,
        account_id=account_id,
        headers=headers,
        verify_ssl=verify_ssl,
        timeout_seconds=timeout_seconds,
    )


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

    def connect(self) -> None:
        self.validate_session()
        self._connected = True

    def disconnect(self) -> None:
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

    def resolve_conid(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("Ticker symbol is required for IBKR Web API conid lookup.")
        cached = self._conid_cache.get(normalized)
        if cached:
            return cached

        payload = self._request_json(
            "GET",
            "/iserver/secdef/search",
            params={"symbol": normalized, "secType": "STK", "name": "true"},
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
                self._conid_cache[normalized] = conid
                return conid

        if fallback_conid is None:
            raise RuntimeError(f"IBKR Web API could not resolve a contract id for ticker {normalized!r}.")

        self._conid_cache[normalized] = fallback_conid
        return fallback_conid

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
            json=[ticket],
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

        if not isinstance(payload, dict) or "order_id" not in payload:
            raise RuntimeError("IBKR Web API order submission did not return an acknowledgement.")
        return payload

    def cancel_order(self, order_id: str) -> dict[str, object]:
        payload = self._request_json(
            "DELETE",
            f"/iserver/account/{self._settings.account_id}/order/{order_id}",
        )
        if not isinstance(payload, dict):
            raise RuntimeError("IBKR Web API cancel-order response must be an object.")
        return payload

    def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        self._pacing_limiter.wait_for_slot(method, path)
        response = self._client.request(method, path, **kwargs)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip()
            if response.status_code == 429:
                raise RuntimeError(
                    f"IBKR Web API pacing limit exceeded for {method} {path}: "
                    f"{response.status_code} {detail}"
                ) from exc
            raise RuntimeError(
                f"IBKR Web API request failed for {method} {path}: "
                f"{response.status_code} {detail}"
            ) from exc
        if not response.content:
            return {}
        return response.json()


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
