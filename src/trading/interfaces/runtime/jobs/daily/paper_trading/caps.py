from __future__ import annotations

import json
from pathlib import Path


def parse_account_trade_caps(value: str) -> dict[str, int]:
    if not value.strip():
        return {}

    caps: dict[str, int] = {}
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError("--account-trade-caps entries must look like account:max")
        account_name, max_text = item.split(":", 1)
        caps[account_name.strip()] = _validate_max_trades(account_name.strip(), int(max_text))
    return caps


def _validate_max_trades(name: str, max_trades: int) -> int:
    if max_trades < 1:
        raise ValueError(f"{name}: max trades must be >= 1")
    return max_trades


def load_trade_caps_config(config_path: Path) -> tuple[int | None, dict[str, int]]:
    if not config_path.exists():
        return None, {}

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Trade caps config must be a JSON object")

    default_caps: int | None = None
    raw_default = raw.get("default")
    if raw_default is not None:
        default_caps = _validate_max_trades("default", int(raw_default))

    account_caps: dict[str, int] = {}
    raw_accounts = raw.get("accounts", {})
    if not isinstance(raw_accounts, dict):
        raise ValueError("Trade caps config 'accounts' must be an object")

    for account_name, caps in raw_accounts.items():
        account_caps[account_name] = _validate_max_trades(account_name, int(caps))

    return default_caps, account_caps


def resolve_trade_caps(
    accounts: list[str],
    configured_default_caps: int | None,
    configured_account_caps: dict[str, int],
    primary_accounts: set[str],
    primary_max_trades: int,
    other_max_trades: int,
    account_trade_cap_overrides: dict[str, int],
) -> dict[str, int]:
    resolved: dict[str, int] = {}
    for account in accounts:
        if account in account_trade_cap_overrides:
            resolved[account] = account_trade_cap_overrides[account]
            continue
        if account in configured_account_caps:
            resolved[account] = configured_account_caps[account]
            continue
        if configured_default_caps is not None:
            resolved[account] = configured_default_caps
            continue
        if account in primary_accounts:
            resolved[account] = primary_max_trades
        else:
            resolved[account] = other_max_trades
    return resolved


def group_accounts_by_caps(
    accounts: list[str],
    caps: dict[str, int],
) -> dict[int, list[str]]:
    grouped: dict[int, list[str]] = {}
    for account in accounts:
        grouped.setdefault(caps[account], []).append(account)
    return grouped
