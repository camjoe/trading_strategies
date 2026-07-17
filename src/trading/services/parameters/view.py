"""Read-through view over the existing parameter stores.

Assembles one legible payload from ``global_settings``, the per-book
settings tables, book mandate columns, and strategy rows. No new store:
every value shown here is read from where it already lives, with the
code-default fallback made explicit.
"""

from __future__ import annotations

import sqlite3
from dataclasses import fields
from typing import Any

from trading.domain.exceptions import NotFoundError
from trading.models.books.book_record import BookRecord
from trading.models.books.book_rotation_settings_record import BookRotationSettingsRecord
from trading.models.parameters.constants import PARAMETER_SOURCE_DB, PARAMETER_SOURCE_DEFAULT
from trading.models.parameters.parameter_entry import ParameterEntry
from trading.models.parameters.parameter_group import ParameterGroup
from trading.models.parameters.parameter_source_view import ParameterSourceView
from trading.repositories.accounts import AccountRepository
from trading.repositories.book_settings import (
    BookOptionSettingsRepository,
    BookRotationSettingsRepository,
)
from trading.repositories.books import BookRepository
from trading.repositories.global_settings import GlobalSettingsRepository
from trading.repositories.strategies import StrategyRepository
from trading.services.books.rotation import BookRotationScheduleConfig, RotationPolicyConfig
from trading.services.operational_settings import (
    fetch_evaluation_confidence_settings,
    fetch_promotion_policy_settings,
    fetch_runtime_throttle_settings,
)
from trading.services.parameters.mutations import ROTATION_POLICY_FIELDS

# Group-level note used whenever a settings row is absent (missing row means
# code defaults apply).
NO_SETTINGS_ROW_NOTE = "no settings row - code defaults apply"

# Row-level audit columns carried by every settings table; not parameters.
_NON_PARAMETER_FIELDS = frozenset({"book_id", "created_at", "updated_at"})


def _render(value: object) -> str:
    if value is None:
        return "none"
    return str(value)


def _entries_from_dataclass(
    instance: object, *, source: str, exclude: frozenset[str] = frozenset()
) -> tuple[ParameterEntry, ...]:
    skip = _NON_PARAMETER_FIELDS | exclude
    return tuple(
        ParameterEntry(name=field.name, value=_render(getattr(instance, field.name)), source=source)
        for field in fields(instance)  # type: ignore[arg-type]
        if field.name not in skip
    )


def _effective_entry(name: str, *, raw: object, default: object) -> ParameterEntry:
    if raw is not None:
        return ParameterEntry(name=name, value=_render(raw), source=PARAMETER_SOURCE_DB)
    return ParameterEntry(name=name, value=_render(default), source=PARAMETER_SOURCE_DEFAULT)


def _global_groups(conn: sqlite3.Connection) -> list[ParameterGroup]:
    has_row = GlobalSettingsRepository(conn).fetch() is not None
    source = PARAMETER_SOURCE_DB if has_row else PARAMETER_SOURCE_DEFAULT
    note = None if has_row else NO_SETTINGS_ROW_NOTE
    throttle = fetch_runtime_throttle_settings(conn)
    evaluation = fetch_evaluation_confidence_settings(conn)
    promotion = fetch_promotion_policy_settings(conn)
    return [
        ParameterGroup(
            scope="global / trade throttle",
            entries=_entries_from_dataclass(throttle, source=source),
            note=note,
        ),
        ParameterGroup(
            scope="global / evaluation confidence",
            entries=_entries_from_dataclass(evaluation, source=source),
            note=note,
        ),
        ParameterGroup(
            scope="global / promotion policy",
            entries=_entries_from_dataclass(promotion, source=source),
            note=note,
        ),
    ]


def _mandate_group(scope_prefix: str, book: BookRecord) -> ParameterGroup:
    entries = (
        ParameterEntry(
            name="goal_min_return_pct", value=_render(book.goal_min_return_pct), source=PARAMETER_SOURCE_DB
        ),
        ParameterEntry(
            name="goal_max_return_pct", value=_render(book.goal_max_return_pct), source=PARAMETER_SOURCE_DB
        ),
        ParameterEntry(name="goal_period", value=_render(book.goal_period), source=PARAMETER_SOURCE_DB),
        ParameterEntry(name="trade_universes", value=_render(book.trade_universes), source=PARAMETER_SOURCE_DB),
    )
    return ParameterGroup(scope=f"{scope_prefix} / mandate", entries=entries)


# Execution settings are books columns since revision 0004; a book row always
# exists, so every entry is db-sourced.
_EXECUTION_FIELDS = (
    "learning_enabled",
    "risk_policy",
    "stop_loss_pct",
    "take_profit_pct",
    "profit_take_pct",
    "max_loss_pct",
    "trade_size_pct",
    "max_position_pct",
    "max_trades_per_run",
    "instrument_mode",
)


def _execution_group(scope: str, book: BookRecord) -> ParameterGroup:
    entries = tuple(
        ParameterEntry(name=name, value=_render(getattr(book, name)), source=PARAMETER_SOURCE_DB)
        for name in _EXECUTION_FIELDS
    )
    return ParameterGroup(scope=scope, entries=entries)


def _settings_group(scope: str, record: Any) -> ParameterGroup:
    if record is None:
        return ParameterGroup(scope=scope, entries=(), note=NO_SETTINGS_ROW_NOTE)
    return ParameterGroup(scope=scope, entries=_entries_from_dataclass(record, source=PARAMETER_SOURCE_DB))


def _rotation_group(scope: str, record: BookRotationSettingsRecord | None) -> ParameterGroup:
    """Rotation group with every field resolved per-field (book-owned, ADR 014).

    Both the scheduling columns (enabled gate, challenger schedule, lookback)
    and the policy columns are nullable with a code-default contract, so each
    entry shows the effective value the runtime resolves, sourced db/default
    per field.
    """
    schedule_defaults = BookRotationScheduleConfig()
    policy_defaults = RotationPolicyConfig()
    scheduling = (
        _effective_entry(
            "rotation_enabled",
            raw=bool(record.rotation_enabled) if record is not None else None,
            default=schedule_defaults.rotation_enabled,
        ),
        _effective_entry(
            "rotation_schedule",
            raw=record.rotation_schedule if record is not None else None,
            # The code default is an empty schedule (incumbent-only).
            default=None,
        ),
        _effective_entry(
            "rotation_lookback_days",
            raw=record.rotation_lookback_days if record is not None else None,
            default=schedule_defaults.lookback_days,
        ),
    )
    policy = tuple(
        _effective_entry(
            name,
            raw=getattr(record, name) if record is not None else None,
            default=getattr(policy_defaults, name),
        )
        for name in ROTATION_POLICY_FIELDS
    )
    note = NO_SETTINGS_ROW_NOTE if record is None else None
    return ParameterGroup(scope=scope, entries=scheduling + policy, note=note)


def _book_groups(conn: sqlite3.Connection, account_name: str, book: BookRecord) -> list[ParameterGroup]:
    prefix = f"account {account_name} / book {book.name}"
    return [
        _mandate_group(prefix, book),
        _execution_group(f"{prefix} / execution", book),
        _settings_group(f"{prefix} / options", BookOptionSettingsRepository(conn).fetch(book_id=book.id)),
        _rotation_group(f"{prefix} / rotation", BookRotationSettingsRepository(conn).fetch(book_id=book.id)),
    ]


def _strategy_groups(conn: sqlite3.Connection) -> list[ParameterGroup]:
    groups: list[ParameterGroup] = []
    for strategy in StrategyRepository(conn).fetch_all():
        entries = (
            ParameterEntry(name="primitive", value=strategy.primitive, source=PARAMETER_SOURCE_DB),
            ParameterEntry(name="style", value=strategy.style, source=PARAMETER_SOURCE_DB),
            ParameterEntry(name="status", value=strategy.status, source=PARAMETER_SOURCE_DB),
            ParameterEntry(name="enabled", value=_render(bool(strategy.enabled)), source=PARAMETER_SOURCE_DB),
            ParameterEntry(name="params", value=strategy.params_json, source=PARAMETER_SOURCE_DB),
        )
        groups.append(ParameterGroup(scope=f"strategy {strategy.strategy_key}", entries=entries))
    return groups


def fetch_parameter_source_view(
    conn: sqlite3.Connection,
    *,
    account_name: str | None = None,
) -> ParameterSourceView:
    """Assemble the unified parameter view.

    With ``account_name`` the book groups are limited to that account (the
    global and strategy groups are always included); unknown names raise
    ``NotFoundError``.
    """
    groups = _global_groups(conn)

    accounts = AccountRepository(conn).fetch_all()
    if account_name is not None:
        accounts = [account for account in accounts if account.name == account_name]
        if not accounts:
            raise NotFoundError(f"Account not found: {account_name}")
    books = BookRepository(conn)
    for account in accounts:
        for book in books.fetch_for_account(account_id=account.id):
            groups.extend(_book_groups(conn, account.name, book))

    groups.extend(_strategy_groups(conn))
    return ParameterSourceView(groups=tuple(groups))
