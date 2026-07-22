from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from common.coercion import coerce_float
from common.time import utc_now_iso
from trading.models.accounts.account_config import AccountConfig
from trading.repositories.book_bridge import default_book_id
from trading.repositories.book_settings import BookRotationSettingsRepository
from trading.services.books.rotation.config_parser import parse_book_rotation_config_from_profile
from trading.services.accounts import (
    configure_account,
    create_account,
    get_account,
    set_account_strategy,
    set_benchmark,
)
from trading.services.profiles.source import AccountProfileSource, JsonAccountProfileSource
from trading.domain.rotation import dump_rotation_schedule
from trading.domain.strategy_signals import validate_strategy_name


def load_account_profiles_from_source(source: AccountProfileSource) -> list[dict[str, object]]:
    return source.load_profiles()


def load_account_profiles(file_path: str) -> list[dict[str, object]]:
    return load_account_profiles_from_source(JsonAccountProfileSource(file_path))


def apply_book_rotation_settings(conn: sqlite3.Connection, name: str, profile: dict[str, object]) -> bool:
    """Apply the profile's nested ``rotation`` object to the default book.

    Rotation scheduling is book-owned (ADR 014): the account profile's
    rotation config lands on the account's default book. Keys absent from the
    ``rotation`` object keep their persisted values (partial edit).
    """
    raw = profile.get("rotation")
    if raw is None:
        return False
    cfg = parse_book_rotation_config_from_profile(profile)
    assert isinstance(raw, Mapping)  # parse rejects non-mapping values

    account = get_account(conn, name)
    book_id = default_book_id(conn, account.id)
    repository = BookRotationSettingsRepository(conn)
    current = repository.fetch(book_id=book_id)

    if "enabled" in raw:
        enabled = int(bool(cfg.enabled))
    else:
        enabled = int(current.rotation_enabled) if current is not None else 0
    if "lookback_days" in raw:
        lookback_days = cfg.lookback_days
    else:
        lookback_days = current.rotation_lookback_days if current is not None else None
    if "schedule" in raw:
        schedule = dump_rotation_schedule(cfg.schedule) if cfg.schedule else None
    else:
        schedule = current.rotation_schedule if current is not None else None

    now_iso = utc_now_iso()
    repository.upsert_rotation_scheduling(
        book_id=book_id,
        rotation_enabled=enabled,
        rotation_lookback_days=lookback_days,
        rotation_schedule=schedule,
        created_at=current.created_at if current is not None else now_iso,
        updated_at=now_iso,
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
            apply_book_rotation_settings(conn, name, profile)
            created += 1
            continue

        fields_updated = False

        if "benchmark_ticker" in profile:
            set_benchmark(conn, name, benchmark)
            fields_updated = True

        if strategy is not None:
            # Through the service so the default book's assignment follows.
            set_account_strategy(conn, name, strategy)
            fields_updated = True

        if AccountConfig.has_any_field(profile):
            configure_account(conn, account_name=name, config=account_config)
            fields_updated = True

        if apply_book_rotation_settings(conn, name, profile):
            fields_updated = True

        if fields_updated:
            updated += 1
        else:
            skipped += 1

    return created, updated, skipped
