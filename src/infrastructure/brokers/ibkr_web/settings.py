"""IBKR Web API operator settings and configuration loading.

Settings come from environment variables first, then an ignored local config file
(``local/ibkr_web_api_config.json``). Sensitive account IDs and session headers stay
outside tracked repo state.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from common.coercion import coerce_bool, coerce_float
from common.paths import LOCAL_DIR

# Default local Client Portal Gateway base URL.
_DEFAULT_WEB_API_BASE_URL = "https://localhost:5000/v1/api"

# Default timeout for individual Web API requests in seconds.
_DEFAULT_TIMEOUT_SECONDS = 10.0

# Default ignored local config file for operator-managed Web API settings.
_DEFAULT_WEB_API_CONFIG_PATH = LOCAL_DIR / "ibkr_web_api_config.json"


@dataclass(frozen=True)
class IbWebApiSettings:
    """Operator-managed Web API settings loaded from env or ignored local config."""

    base_url: str
    account_id: str
    headers: dict[str, str]
    verify_ssl: bool = False
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    keepalive_enabled: bool = True
    keepalive_interval_seconds: float = 60.0


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
    keepalive_enabled_raw = _config_value(
        "TRADING_IBKR_WEB_API_KEEPALIVE_ENABLED",
        payload,
        "keepalive_enabled",
    )
    keepalive_interval_raw = _config_value(
        "TRADING_IBKR_WEB_API_KEEPALIVE_INTERVAL_SECONDS",
        payload,
        "keepalive_interval_seconds",
    )

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

    keepalive_enabled = True
    if keepalive_enabled_raw is not None:
        coerced_keepalive_enabled = coerce_bool(keepalive_enabled_raw)
        if coerced_keepalive_enabled is None:
            raise ValueError("IBKR Web API keepalive_enabled must be a boolean value.")
        keepalive_enabled = bool(coerced_keepalive_enabled)

    keepalive_interval_seconds = 60.0
    if keepalive_interval_raw is not None:
        coerced_keepalive_interval = coerce_float(keepalive_interval_raw)
        if coerced_keepalive_interval is None or coerced_keepalive_interval <= 0:
            raise ValueError("IBKR Web API keepalive_interval_seconds must be a positive number.")
        keepalive_interval_seconds = float(coerced_keepalive_interval)

    return IbWebApiSettings(
        base_url=base_url,
        account_id=account_id,
        headers=headers,
        verify_ssl=verify_ssl,
        timeout_seconds=timeout_seconds,
        keepalive_enabled=keepalive_enabled,
        keepalive_interval_seconds=keepalive_interval_seconds,
    )
