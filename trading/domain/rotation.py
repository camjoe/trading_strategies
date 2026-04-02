from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Mapping

from trading.utils.coercion import coerce_int

from common.constants import SECONDS_PER_DAY

ROTATION_MODES = {"time", "optimal"}
OPTIMALITY_MODES = {"previous_period_best", "average_return"}


def _value(account: Mapping[str, object], key: str) -> object | None:
    """Safely get a value from an account mapping, handling both dict and row objects."""
    if hasattr(account, "get"):
        return account.get(key)
    try:
        return account[key]
    except (KeyError, TypeError):
        return None


def _as_int(value: object | None, default: int = 0) -> int:
    converted = coerce_int(value)
    return default if converted is None else converted


def resolve_rotation_mode(account: Mapping[str, object]) -> str:
    mode_raw = _value(account, "rotation_mode")
    mode = str(mode_raw or "time").strip().lower()
    return mode if mode in ROTATION_MODES else "time"


def resolve_optimality_mode(account: Mapping[str, object]) -> str:
    mode_raw = _value(account, "rotation_optimality_mode")
    mode = str(mode_raw or "previous_period_best").strip().lower()
    return mode if mode in OPTIMALITY_MODES else "previous_period_best"


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _as_utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_rotation_schedule(raw_value: object | None) -> list[str]:
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
            raise ValueError("rotation_schedule must be valid JSON.") from exc
        if not isinstance(decoded, list):
            raise ValueError("rotation_schedule must decode to a list of strategy ids.")
        raw_items = decoded
    else:
        raise ValueError("rotation_schedule must be a list or JSON string.")

    schedule: list[str] = []
    for item in raw_items:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("rotation_schedule items must be non-empty strings.")
        strategy_id = item.strip()
        if strategy_id not in schedule:
            schedule.append(strategy_id)

    return schedule


def dump_rotation_schedule(schedule: list[str]) -> str:
    return json.dumps(schedule, separators=(",", ":"))


def resolve_active_strategy(account: Mapping[str, object]) -> str:
    fallback = str(_value(account, "strategy") or "").strip()
    schedule = parse_rotation_schedule(_value(account, "rotation_schedule"))
    if not schedule:
        active = str(_value(account, "rotation_active_strategy") or "").strip()
        return active or fallback

    active = str(_value(account, "rotation_active_strategy") or "").strip()
    if active and active in schedule:
        return active

    idx_raw = _value(account, "rotation_active_index")
    idx = _as_int(idx_raw, default=0)
    return schedule[idx % len(schedule)]


def is_rotation_due(account: Mapping[str, object], *, as_of_iso: str) -> bool:
    enabled_raw = _value(account, "rotation_enabled")
    enabled = bool(_as_int(enabled_raw, default=0))
    if not enabled:
        return False

    schedule = parse_rotation_schedule(_value(account, "rotation_schedule"))
    if len(schedule) < 2:
        return False

    interval_raw = _value(account, "rotation_interval_days")
    if interval_raw is None:
        return False
    interval_days = _as_int(interval_raw, default=0)
    if interval_days <= 0:
        return False

    now = _parse_iso(as_of_iso)
    if now is None:
        raise ValueError("as_of_iso must be a valid ISO datetime.")

    last_rotation = _parse_iso(str(_value(account, "rotation_last_at") or ""))
    if last_rotation is None:
        return True

    elapsed_seconds = (now - last_rotation).total_seconds()
    return elapsed_seconds >= (interval_days * SECONDS_PER_DAY)


def next_rotation_state(account: Mapping[str, object], *, as_of_iso: str) -> dict[str, object]:
    schedule = parse_rotation_schedule(_value(account, "rotation_schedule"))
    if len(schedule) < 2:
        return {
            "rotation_active_index": 0,
            "rotation_active_strategy": resolve_active_strategy(account),
            "rotation_last_at": str(_value(account, "rotation_last_at") or ""),
        }

    idx_raw = _value(account, "rotation_active_index")
    idx = _as_int(idx_raw, default=0)
    next_idx = (idx + 1) % len(schedule)
    return {
        "rotation_active_index": next_idx,
        "rotation_active_strategy": schedule[next_idx],
        "rotation_last_at": _as_utc_iso(_parse_iso(as_of_iso) or datetime.now(UTC)),
    }
