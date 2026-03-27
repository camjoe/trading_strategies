import json
import sqlite3
from pathlib import Path
from trading.accounts import configure_account, create_account, get_account, set_benchmark
from trading.database.db_coercion import coerce_bool, coerce_float, coerce_int, coerce_str
from trading.rotation import OPTIMALITY_MODES, ROTATION_MODES, dump_rotation_schedule, parse_rotation_schedule


_CONFIGURE_KEYS = {
    "descriptive_name", "goal_min_return_pct", "goal_max_return_pct", "goal_period",
    "learning_enabled", "risk_policy", "stop_loss_pct", "take_profit_pct",
    "instrument_mode", "option_strike_offset_pct", "option_min_dte", "option_max_dte",
    "option_type", "target_delta_min", "target_delta_max", "max_premium_per_trade",
    "max_contracts_per_trade", "iv_rank_min", "iv_rank_max", "roll_dte_threshold",
    "profit_take_pct", "max_loss_pct",
}

_ROTATION_KEYS = {
    "rotation_enabled",
    "rotation_mode",
    "rotation_optimality_mode",
    "rotation_interval_days",
    "rotation_lookback_days",
    "rotation_schedule",
    "rotation_active_index",
    "rotation_last_at",
    "rotation_active_strategy",
}

def load_account_profiles(file_path: str) -> list[dict[str, object]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Profile file not found: {file_path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(raw, dict):
        profiles = raw.get("accounts", [])
    else:
        profiles = raw

    if not isinstance(profiles, list):
        raise ValueError("Profile file must be a list or an object with an 'accounts' list.")

    out: list[dict[str, object]] = []
    for i, item in enumerate(profiles, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Account profile at index {i} is not an object.")
        if "name" not in item or not str(item["name"]).strip():
            raise ValueError(f"Account profile at index {i} is missing required 'name'.")
        out.append(item)

    return out


def _extract_profile_fields(profile: dict[str, object]) -> dict[str, object]:
    """Normalize and type-coerce all configurable fields from a raw profile dict."""
    g = profile.get
    return {
        "descriptive_name": coerce_str(g("descriptive_name")),
        "goal_min_return_pct": coerce_float(g("goal_min_return_pct")),
        "goal_max_return_pct": coerce_float(g("goal_max_return_pct")),
        "goal_period": coerce_str(g("goal_period")),
        "learning_enabled": coerce_bool(g("learning_enabled")),
        "risk_policy": coerce_str(g("risk_policy")),
        "stop_loss_pct": coerce_float(g("stop_loss_pct")),
        "take_profit_pct": coerce_float(g("take_profit_pct")),
        "instrument_mode": coerce_str(g("instrument_mode")),
        "option_strike_offset_pct": coerce_float(g("option_strike_offset_pct")),
        "option_min_dte": coerce_int(g("option_min_dte")),
        "option_max_dte": coerce_int(g("option_max_dte")),
        "option_type": coerce_str(g("option_type")),
        "target_delta_min": coerce_float(g("target_delta_min")),
        "target_delta_max": coerce_float(g("target_delta_max")),
        "max_premium_per_trade": coerce_float(g("max_premium_per_trade")),
        "max_contracts_per_trade": coerce_int(g("max_contracts_per_trade")),
        "iv_rank_min": coerce_float(g("iv_rank_min")),
        "iv_rank_max": coerce_float(g("iv_rank_max")),
        "roll_dte_threshold": coerce_int(g("roll_dte_threshold")),
        "profit_take_pct": coerce_float(g("profit_take_pct")),
        "max_loss_pct": coerce_float(g("max_loss_pct")),
    }


def _extract_rotation_fields(profile: dict[str, object]) -> dict[str, object]:
    enabled = coerce_bool(profile.get("rotation_enabled"))
    rotation_mode_raw = coerce_str(profile.get("rotation_mode"))
    optimality_mode_raw = coerce_str(profile.get("rotation_optimality_mode"))
    interval_days = coerce_int(profile.get("rotation_interval_days"))
    lookback_days = coerce_int(profile.get("rotation_lookback_days"))
    active_index = coerce_int(profile.get("rotation_active_index"))
    last_at = coerce_str(profile.get("rotation_last_at"))
    active_strategy = coerce_str(profile.get("rotation_active_strategy"))
    schedule = parse_rotation_schedule(profile.get("rotation_schedule"))

    rotation_mode = (rotation_mode_raw or "time").strip().lower()
    if rotation_mode not in ROTATION_MODES:
        raise ValueError("rotation_mode must be one of: time, optimal")

    optimality_mode = (optimality_mode_raw or "previous_period_best").strip().lower()
    if optimality_mode not in OPTIMALITY_MODES:
        allowed = ", ".join(sorted(OPTIMALITY_MODES))
        raise ValueError(f"rotation_optimality_mode must be one of: {allowed}")

    if enabled and (interval_days is None or interval_days <= 0):
        raise ValueError("rotation_interval_days must be > 0 when rotation_enabled is true")
    if lookback_days is not None and lookback_days <= 0:
        raise ValueError("rotation_lookback_days must be > 0")
    if active_index is not None and active_index < 0:
        raise ValueError("rotation_active_index must be >= 0")

    if schedule and active_index is not None and active_index >= len(schedule):
        active_index = active_index % len(schedule)

    if schedule and not active_strategy:
        if active_index is None:
            active_index = 0
        active_strategy = schedule[active_index]

    if active_strategy and schedule and active_strategy not in schedule:
        raise ValueError("rotation_active_strategy must be a member of rotation_schedule")

    if schedule and active_strategy and active_index is None:
        active_index = schedule.index(active_strategy)

    return {
        "rotation_enabled": enabled,
        "rotation_mode": rotation_mode,
        "rotation_optimality_mode": optimality_mode,
        "rotation_interval_days": interval_days,
        "rotation_lookback_days": lookback_days,
        "rotation_schedule": dump_rotation_schedule(schedule) if schedule else None,
        "rotation_active_index": active_index,
        "rotation_last_at": last_at.strip() if last_at is not None else None,
        "rotation_active_strategy": active_strategy.strip() if active_strategy is not None else None,
    }


def _apply_rotation_fields(conn: sqlite3.Connection, name: str, profile: dict[str, object]) -> bool:
    if not any(key in profile for key in _ROTATION_KEYS):
        return False

    account = get_account(conn, name)
    rotation_fields = _extract_rotation_fields(profile)

    updates: list[str] = []
    params: list[object] = []

    has_schedule_input = "rotation_schedule" in profile
    has_index_input = "rotation_active_index" in profile
    for key, value in rotation_fields.items():
        if key == "rotation_schedule" and "rotation_schedule" not in profile:
            continue
        if key == "rotation_active_strategy" and "rotation_active_strategy" not in profile and not has_schedule_input and not has_index_input:
            continue
        if key == "rotation_last_at" and "rotation_last_at" not in profile:
            continue
        if key == "rotation_enabled" and "rotation_enabled" not in profile:
            continue
        if key == "rotation_interval_days" and "rotation_interval_days" not in profile:
            continue
        if key == "rotation_lookback_days" and "rotation_lookback_days" not in profile:
            continue
        if key == "rotation_mode" and "rotation_mode" not in profile:
            continue
        if key == "rotation_optimality_mode" and "rotation_optimality_mode" not in profile:
            continue
        if key == "rotation_active_index" and "rotation_active_index" not in profile and not has_schedule_input:
            continue

        updates.append(f"{key} = ?")
        params.append(value)

    if not updates:
        return False

    params.append(account["id"])
    conn.execute(f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?", tuple(params))
    conn.commit()
    return True


def apply_account_profiles(
    conn: sqlite3.Connection,
    profiles: list[dict[str, object]],
    create_missing: bool,
) -> tuple[int, int, int]:
    created = 0
    updated = 0
    skipped = 0

    for profile in profiles:
        name = str(profile["name"]).strip()
        benchmark = str(profile.get("benchmark_ticker", "SPY")).strip().upper()
        strategy = str(profile.get("strategy", "Unspecified")).strip()
        initial_cash = coerce_float(profile.get("initial_cash", 5000.0))
        if initial_cash is None:
            raise ValueError("initial_cash cannot be null")

        try:
            get_account(conn, name)
            exists = True
        except ValueError:
            exists = False

        if not exists:
            if not create_missing:
                skipped += 1
                continue

            fields = _extract_profile_fields(profile)
            create_kwargs = {**fields}
            create_kwargs["goal_period"] = fields["goal_period"] or "monthly"
            create_kwargs["learning_enabled"] = fields["learning_enabled"] if fields["learning_enabled"] is not None else False
            create_kwargs["risk_policy"] = fields["risk_policy"] or "none"
            create_kwargs["instrument_mode"] = fields["instrument_mode"] or "equity"
            create_account(conn, name=name, strategy=strategy, initial_cash=initial_cash, benchmark_ticker=benchmark, **create_kwargs)
            _apply_rotation_fields(conn, name, profile)
            created += 1
            continue

        fields_updated = False

        if "benchmark_ticker" in profile:
            set_benchmark(conn, name, benchmark)
            fields_updated = True

        if "strategy" in profile and strategy:
            account = get_account(conn, name)
            conn.execute("UPDATE accounts SET strategy = ? WHERE id = ?", (strategy, account["id"]))
            conn.commit()
            fields_updated = True

        if any(key in profile for key in _CONFIGURE_KEYS):
            fields = _extract_profile_fields(profile)
            configure_account(conn, account_name=name, **fields)
            fields_updated = True

        if _apply_rotation_fields(conn, name, profile):
            fields_updated = True

        if fields_updated:
            updated += 1
        else:
            skipped += 1

    return created, updated, skipped
