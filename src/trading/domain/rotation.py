from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Callable, Mapping

from common.coercion import coerce_int
from common.constants import SECONDS_PER_DAY, SECONDS_PER_MINUTE
from common.time import as_utc_iso
from common.time import parse_utc_iso

if TYPE_CHECKING:
    from trading.models.rotation.rotation_config import RotationConfig

ROTATION_MODES = {"time", "optimal", "regime"}
OPTIMALITY_MODES = {"previous_period_best", "average_return", "hybrid_weighted"}
ROTATION_REGIME_STATES = {"risk_on", "neutral", "risk_off"}
ROTATION_OVERLAY_MODES = {"none", "news", "social", "news_social"}


def _account_field(account: Mapping[str, object], key: str) -> object | None:
    """Safely read an account field from either dict-like rows or mappings."""
    if hasattr(account, "get"):
        return account.get(key)
    try:
        return account[key]
    except KeyError, TypeError:
        return None


def _account_text(account: Mapping[str, object], key: str) -> str:
    return str(_account_field(account, key) or "").strip()


def _coerce_default_int(value: object | None, default: int = 0) -> int:
    converted = coerce_int(value)
    return default if converted is None else converted


def _normalize_allowed_mode(raw_value: object | None, *, default: str, allowed: set[str]) -> str:
    mode = str(raw_value or default).strip().lower()
    return mode if mode in allowed else default


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return parse_utc_iso(text)
    except ValueError:
        return None


def _parse_unique_string_list(
    raw_value: object | None,
    *,
    field_name: str,
    item_label: str,
    normalizer: Callable[[str], str] | None = None,
) -> list[str]:
    if raw_value is None:
        return []

    if isinstance(raw_value, list):
        raw_items = raw_value
    elif isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} must be valid JSON.") from exc
        if not isinstance(decoded, list):
            raise ValueError(f"{field_name} must decode to a list of {item_label}.")
        raw_items = decoded
    else:
        raise ValueError(f"{field_name} must be a list or JSON string.")

    items: list[str] = []
    for item in raw_items:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} items must be non-empty strings.")
        value = item.strip()
        if normalizer is not None:
            value = normalizer(value)
        if value and value not in items:
            items.append(value)

    return items


def _rotation_schedule(account: Mapping[str, object]) -> list[str]:
    return parse_rotation_schedule(_account_field(account, "rotation_schedule"))


def _rotation_last_at(account: Mapping[str, object]) -> datetime | None:
    return _parse_iso(_account_text(account, "rotation_last_at"))


def _rotation_interval_seconds(account: Mapping[str, object]) -> int:
    interval_minutes = _coerce_default_int(_account_field(account, "rotation_interval_minutes"), default=0)
    if interval_minutes > 0:
        return interval_minutes * SECONDS_PER_MINUTE

    interval_days = _coerce_default_int(_account_field(account, "rotation_interval_days"), default=0)
    if interval_days > 0:
        return interval_days * SECONDS_PER_DAY

    return 0


def resolve_rotation_mode(account: Mapping[str, object]) -> str:
    return _normalize_allowed_mode(
        _account_field(account, "rotation_mode"),
        default="time",
        allowed=ROTATION_MODES,
    )


def resolve_optimality_mode(account: Mapping[str, object]) -> str:
    return _normalize_allowed_mode(
        _account_field(account, "rotation_optimality_mode"),
        default="previous_period_best",
        allowed=OPTIMALITY_MODES,
    )


def resolve_rotation_regime_strategy(account: Mapping[str, object], regime_state: str) -> str | None:
    if regime_state not in ROTATION_REGIME_STATES:
        return None
    strategy = _account_text(account, f"rotation_regime_strategy_{regime_state}")
    return strategy or None


def resolve_rotation_overlay_mode(account: Mapping[str, object]) -> str:
    return _normalize_allowed_mode(
        _account_field(account, "rotation_overlay_mode"),
        default="none",
        allowed=ROTATION_OVERLAY_MODES,
    )


def parse_rotation_schedule(raw_value: object | None) -> list[str]:
    return _parse_unique_string_list(
        raw_value,
        field_name="rotation_schedule",
        item_label="strategy ids",
    )


def dump_rotation_schedule(schedule: list[str]) -> str:
    return json.dumps(schedule, separators=(",", ":"))


def parse_rotation_overlay_watchlist(raw_value: object | None) -> list[str]:
    return _parse_unique_string_list(
        raw_value,
        field_name="rotation_overlay_watchlist",
        item_label="tickers",
        normalizer=lambda value: value.upper(),
    )


def dump_rotation_overlay_watchlist(watchlist: list[str]) -> str:
    return json.dumps(watchlist, separators=(",", ":"))


def rotation_config_to_db_dict(cfg: RotationConfig) -> dict[str, object]:
    """Finalize ``RotationConfig.to_db_dict()`` for persistence.

    The model owns the field→column mapping; this applies the domain-owned
    JSON encoding to the two list-valued columns (schedule, overlay watchlist).
    """
    values = cfg.to_db_dict()
    values["rotation_schedule"] = dump_rotation_schedule(cfg.schedule) if cfg.schedule else None
    if cfg.overlay_watchlist is not None:
        values["rotation_overlay_watchlist"] = dump_rotation_overlay_watchlist(cfg.overlay_watchlist)
    return values


def resolve_rotation_overlay_watchlist(account: Mapping[str, object]) -> list[str]:
    return parse_rotation_overlay_watchlist(_account_field(account, "rotation_overlay_watchlist"))


def resolve_active_strategy(account: Mapping[str, object]) -> str:
    fallback = _account_text(account, "strategy")
    schedule = _rotation_schedule(account)
    if not schedule:
        active = _account_text(account, "rotation_active_strategy")
        return active or fallback

    active = _account_text(account, "rotation_active_strategy")
    if active and active in schedule:
        return active

    idx = _coerce_default_int(_account_field(account, "rotation_active_index"), default=0)
    return schedule[idx % len(schedule)]


def is_rotation_due(account: Mapping[str, object], *, as_of_iso: str) -> bool:
    rotation_enabled = bool(_coerce_default_int(_account_field(account, "rotation_enabled"), default=0))
    if not rotation_enabled:
        return False

    schedule = _rotation_schedule(account)
    if len(schedule) < 2:
        return False

    interval_seconds = _rotation_interval_seconds(account)
    if interval_seconds <= 0:
        return False

    now = _parse_iso(as_of_iso)
    if now is None:
        raise ValueError("as_of_iso must be a valid ISO datetime.")

    last_rotation = _rotation_last_at(account)
    if last_rotation is None:
        return True

    elapsed_seconds = (now - last_rotation).total_seconds()
    return elapsed_seconds >= interval_seconds


def next_rotation_state(account: Mapping[str, object], *, as_of_iso: str) -> dict[str, object]:
    schedule = _rotation_schedule(account)
    if len(schedule) < 2:
        return {
            "rotation_active_index": 0,
            "rotation_active_strategy": resolve_active_strategy(account),
            "rotation_last_at": _account_text(account, "rotation_last_at"),
        }

    idx = _coerce_default_int(_account_field(account, "rotation_active_index"), default=0)
    next_idx = (idx + 1) % len(schedule)
    return {
        "rotation_active_index": next_idx,
        "rotation_active_strategy": schedule[next_idx],
        "rotation_last_at": as_utc_iso(_parse_iso(as_of_iso) or datetime.now(UTC)),
    }
