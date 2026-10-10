from __future__ import annotations


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


def resolve_trade_caps(
    accounts: list[str],
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
