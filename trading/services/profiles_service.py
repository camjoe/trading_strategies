from __future__ import annotations

import sqlite3

from trading.backtesting.domain.strategy_signals import validate_strategy_name
from trading.services.accounts_service import configure_account, create_account, get_account, set_benchmark
from trading.utils.coercion import coerce_float
from trading.models.account_config import AccountConfig
from trading.models.rotation_config import RotationConfig
from trading.services.profile_source import AccountProfileSource, JsonAccountProfileSource
from trading.repositories.accounts_repository import update_account_fields

ROTATION_KEYS = {
    "rotation_enabled",
    "rotation_mode",
    "rotation_optimality_mode",
    "rotation_interval_days",
    "rotation_interval_minutes",
    "rotation_lookback_days",
    "rotation_schedule",
    "rotation_regime_strategy_risk_on",
    "rotation_regime_strategy_neutral",
    "rotation_regime_strategy_risk_off",
    "rotation_overlay_mode",
    "rotation_overlay_min_tickers",
    "rotation_overlay_confidence_threshold",
    "rotation_overlay_watchlist",
    "rotation_active_index",
    "rotation_last_at",
    "rotation_active_strategy",
}


def load_account_profiles_from_source(source: AccountProfileSource) -> list[dict[str, object]]:
    return source.load_profiles()


def load_account_profiles(file_path: str) -> list[dict[str, object]]:
    return load_account_profiles_from_source(JsonAccountProfileSource(file_path))


def apply_rotation_fields(conn: sqlite3.Connection, name: str, profile: dict[str, object]) -> bool:
    if not any(key in profile for key in ROTATION_KEYS):
        return False

    account = get_account(conn, name)
    cfg = RotationConfig.from_profile(profile)

    has_schedule_input = "rotation_schedule" in profile
    has_index_input = "rotation_active_index" in profile

    write_keys: set[str] = {k for k in ROTATION_KEYS if k in profile}
    if has_schedule_input or has_index_input:
        write_keys.add("rotation_active_strategy")
    if has_schedule_input:
        write_keys.add("rotation_active_index")

    field_values = cfg.to_db_dict()

    updates: list[str] = []
    params: list[object] = []
    for key, value in field_values.items():
        if key not in write_keys:
            continue
        updates.append(f"{key} = ?")
        params.append(value)

    if not updates:
        return False

    update_account_fields(
        conn,
        account_id=account["id"],
        updates=updates,
        params=params,
    )
    return True


def _validated_profile_strategy(profile: dict[str, object]) -> str | None:
    strategy_value = profile.get("strategy")
    if strategy_value is None:
        return None

    strategy_name = str(strategy_value).strip()
    if not strategy_name:
        return None

    validate_strategy_name(strategy_name)
    return strategy_name


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
        strategy = _validated_profile_strategy(profile)
        account_config = AccountConfig.from_mapping(profile)
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
            if strategy is None:
                raise ValueError(f"Profile '{name}' must define a valid strategy.")

            create_account(
                conn,
                name,
                strategy,
                initial_cash,
                benchmark,
                config=account_config,
            )
            apply_rotation_fields(conn, name, profile)
            created += 1
            continue

        fields_updated = False

        if "benchmark_ticker" in profile:
            set_benchmark(conn, name, benchmark)
            fields_updated = True

        if strategy is not None:
            account = get_account(conn, name)
            update_account_fields(
                conn,
                account_id=account["id"],
                updates=["strategy = ?"],
                params=[strategy],
            )
            fields_updated = True

        if AccountConfig.has_any_field(profile):
            configure_account(conn, account_name=name, config=account_config)
            fields_updated = True

        if apply_rotation_fields(conn, name, profile):
            fields_updated = True

        if fields_updated:
            updated += 1
        else:
            skipped += 1

    return created, updated, skipped
