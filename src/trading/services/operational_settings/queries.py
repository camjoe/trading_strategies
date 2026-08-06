"""Operational settings queries for operational-settings consumers.

Owns caller-facing reads of persisted operational settings beneath the stable
``trading.services.operational_settings`` package surface.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import fields
from typing import TYPE_CHECKING

from trading.domain.evaluation.confidence import EvaluationConfidenceSettings
from trading.domain.promotion_policy import PromotionPolicySettings
from trading.repositories.global_settings import GlobalSettingsRepository
from trading.services.operational_settings.models import RuntimeThrottleSettings

if TYPE_CHECKING:
    from _typeshed import DataclassInstance


def _override[T](value: T | None, default: T) -> T:
    """Return an explicit database override or its code-owned default."""
    return default if value is None else value


def _settings_from_global_record[T: DataclassInstance](
    conn: sqlite3.Connection,
    settings_cls: Callable[..., T],
    *,
    column_prefix: str,
) -> T:
    """Build a settings dataclass from global_settings; column = prefix + field name.

    The mapping is derived rather than written out per field on purpose. Every
    field of these settings classes has a code default, so a field left unwired
    would silently ignore its operator override instead of failing — and these
    are promotion thresholds and confidence weights. Deriving the mapping keeps
    a newly added field wired by construction.
    """
    defaults = settings_cls()
    if not hasattr(conn, "execute"):
        return defaults
    record = GlobalSettingsRepository(conn).fetch()
    if record is None:
        return defaults
    return settings_cls(
        **{
            field.name: _override(
                getattr(record, f"{column_prefix}{field.name}"),
                getattr(defaults, field.name),
            )
            for field in fields(defaults)
        }
    )


def fetch_runtime_throttle_settings(conn: sqlite3.Connection) -> RuntimeThrottleSettings:
    if not hasattr(conn, "execute"):
        return RuntimeThrottleSettings()
    record = GlobalSettingsRepository(conn).fetch()
    if record is None:
        return RuntimeThrottleSettings()
    return RuntimeThrottleSettings(
        max_trades_per_day=record.runtime_max_trades_per_day,
        max_trades_per_minute=record.runtime_max_trades_per_minute,
    )


def fetch_evaluation_confidence_settings(conn: sqlite3.Connection) -> EvaluationConfidenceSettings:
    return _settings_from_global_record(conn, EvaluationConfidenceSettings, column_prefix="evaluation_")


def fetch_promotion_policy_settings(conn: sqlite3.Connection) -> PromotionPolicySettings:
    return _settings_from_global_record(conn, PromotionPolicySettings, column_prefix="promotion_")


__all__ = [
    "fetch_evaluation_confidence_settings",
    "fetch_promotion_policy_settings",
    "fetch_runtime_throttle_settings",
]
