from __future__ import annotations

import json
from pathlib import Path


def parse_account_trade_caps(value: str) -> dict[str, tuple[int, int]]:
    if not value.strip():
        return {}

    caps: dict[str, tuple[int, int]] = {}
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if ":" not in item or "-" not in item:
            raise ValueError("--account-trade-caps entries must look like account:min-max")
        account_name, raw_range = item.split(":", 1)
        min_text, max_text = raw_range.split("-", 1)
        caps[account_name.strip()] = _validate_trade_cap_range(
            account_name.strip(),
            int(min_text),
            int(max_text),
        )
    return caps


def _validate_trade_cap_range(name: str, min_trades: int, max_trades: int) -> tuple[int, int]:
    if min_trades < 1:
        raise ValueError(f"{name}: min trades must be >= 1")
    if max_trades < min_trades:
        raise ValueError(f"{name}: max trades must be >= min trades")
    return min_trades, max_trades


def load_trade_caps_config(config_path: Path) -> tuple[tuple[int, int] | None, dict[str, tuple[int, int]]]:
    if not config_path.exists():
        return None, {}

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Trade caps config must be a JSON object")

    default_caps: tuple[int, int] | None = None
    raw_default = raw.get("default")
    if raw_default is not None:
        if not isinstance(raw_default, dict) or "min" not in raw_default or "max" not in raw_default:
            raise ValueError("Trade caps config 'default' must contain min and max")
        default_caps = _validate_trade_cap_range(
            "default",
            int(raw_default["min"]),
            int(raw_default["max"]),
        )

    account_caps: dict[str, tuple[int, int]] = {}
    raw_accounts = raw.get("accounts", {})
    if not isinstance(raw_accounts, dict):
        raise ValueError("Trade caps config 'accounts' must be an object")

    for account_name, caps in raw_accounts.items():
        if not isinstance(caps, dict) or "min" not in caps or "max" not in caps:
            raise ValueError(f"Trade caps config for account '{account_name}' must contain min and max")
        account_caps[account_name] = _validate_trade_cap_range(
            account_name,
            int(caps["min"]),
            int(caps["max"]),
        )

    return default_caps, account_caps


def resolve_trade_caps(
    accounts: list[str],
    configured_default_caps: tuple[int, int] | None,
    configured_account_caps: dict[str, tuple[int, int]],
    primary_accounts: set[str],
    primary_min_trades: int,
    primary_max_trades: int,
    other_min_trades: int,
    other_max_trades: int,
    account_trade_cap_overrides: dict[str, tuple[int, int]],
) -> dict[str, tuple[int, int]]:
    resolved: dict[str, tuple[int, int]] = {}
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
            resolved[account] = (primary_min_trades, primary_max_trades)
        else:
            resolved[account] = (other_min_trades, other_max_trades)
    return resolved


def group_accounts_by_caps(
    accounts: list[str],
    caps: dict[str, tuple[int, int]],
) -> dict[tuple[int, int], list[str]]:
    grouped: dict[tuple[int, int], list[str]] = {}
    for account in accounts:
        grouped.setdefault(caps[account], []).append(account)
    return grouped
