from __future__ import annotations

import sqlite3

from trading.models.units.unit_execution_settings_record import UnitExecutionSettingsRecord
from trading.models.units.unit_option_settings_record import UnitOptionSettingsRecord
from trading.models.units.unit_rotation_settings_record import UnitRotationSettingsRecord

# Per-concern typed settings tables, 1:1 with trading_units (D4, 2026-07-03).
# A missing row means "use code defaults"; change-audit arrives with P7.


class UnitExecutionSettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def fetch(self, *, unit_id: int) -> UnitExecutionSettingsRecord | None:
        row = self._conn.execute(
            "SELECT * FROM unit_execution_settings WHERE unit_id = ?",
            (int(unit_id),),
        ).fetchone()
        return UnitExecutionSettingsRecord.from_mapping(dict(row)) if row is not None else None

    def upsert(
        self,
        *,
        unit_id: int,
        learning_enabled: int = 0,
        risk_policy: str = "none",
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        profit_take_pct: float | None = None,
        max_loss_pct: float | None = None,
        trade_size_pct: float | None = None,
        max_position_pct: float | None = None,
        max_trades_per_run: int | None = None,
        instrument_mode: str = "equity",
        created_at: str,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO unit_execution_settings (
                unit_id, learning_enabled, risk_policy, stop_loss_pct, take_profit_pct,
                profit_take_pct, max_loss_pct, trade_size_pct, max_position_pct,
                max_trades_per_run, instrument_mode, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(unit_id) DO UPDATE SET
                learning_enabled = excluded.learning_enabled,
                risk_policy = excluded.risk_policy,
                stop_loss_pct = excluded.stop_loss_pct,
                take_profit_pct = excluded.take_profit_pct,
                profit_take_pct = excluded.profit_take_pct,
                max_loss_pct = excluded.max_loss_pct,
                trade_size_pct = excluded.trade_size_pct,
                max_position_pct = excluded.max_position_pct,
                max_trades_per_run = excluded.max_trades_per_run,
                instrument_mode = excluded.instrument_mode,
                updated_at = excluded.updated_at
            """,
            (
                int(unit_id),
                int(learning_enabled),
                risk_policy,
                stop_loss_pct,
                take_profit_pct,
                profit_take_pct,
                max_loss_pct,
                trade_size_pct,
                max_position_pct,
                max_trades_per_run,
                instrument_mode,
                created_at,
                updated_at,
            ),
        )
        self._conn.commit()


class UnitOptionSettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def fetch(self, *, unit_id: int) -> UnitOptionSettingsRecord | None:
        row = self._conn.execute(
            "SELECT * FROM unit_option_settings WHERE unit_id = ?",
            (int(unit_id),),
        ).fetchone()
        return UnitOptionSettingsRecord.from_mapping(dict(row)) if row is not None else None

    def upsert(
        self,
        *,
        unit_id: int,
        option_strike_offset_pct: float | None = None,
        option_min_dte: int | None = None,
        option_max_dte: int | None = None,
        option_type: str | None = None,
        target_delta_min: float | None = None,
        target_delta_max: float | None = None,
        max_premium_per_trade: float | None = None,
        max_contracts_per_trade: int | None = None,
        iv_rank_min: float | None = None,
        iv_rank_max: float | None = None,
        roll_dte_threshold: int | None = None,
        created_at: str,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO unit_option_settings (
                unit_id, option_strike_offset_pct, option_min_dte, option_max_dte,
                option_type, target_delta_min, target_delta_max, max_premium_per_trade,
                max_contracts_per_trade, iv_rank_min, iv_rank_max, roll_dte_threshold,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(unit_id) DO UPDATE SET
                option_strike_offset_pct = excluded.option_strike_offset_pct,
                option_min_dte = excluded.option_min_dte,
                option_max_dte = excluded.option_max_dte,
                option_type = excluded.option_type,
                target_delta_min = excluded.target_delta_min,
                target_delta_max = excluded.target_delta_max,
                max_premium_per_trade = excluded.max_premium_per_trade,
                max_contracts_per_trade = excluded.max_contracts_per_trade,
                iv_rank_min = excluded.iv_rank_min,
                iv_rank_max = excluded.iv_rank_max,
                roll_dte_threshold = excluded.roll_dte_threshold,
                updated_at = excluded.updated_at
            """,
            (
                int(unit_id),
                option_strike_offset_pct,
                option_min_dte,
                option_max_dte,
                option_type,
                target_delta_min,
                target_delta_max,
                max_premium_per_trade,
                max_contracts_per_trade,
                iv_rank_min,
                iv_rank_max,
                roll_dte_threshold,
                created_at,
                updated_at,
            ),
        )
        self._conn.commit()


class UnitRotationSettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def fetch(self, *, unit_id: int) -> UnitRotationSettingsRecord | None:
        row = self._conn.execute(
            "SELECT * FROM unit_rotation_settings WHERE unit_id = ?",
            (int(unit_id),),
        ).fetchone()
        return UnitRotationSettingsRecord.from_mapping(dict(row)) if row is not None else None

    def upsert(
        self,
        *,
        unit_id: int,
        rotation_enabled: int = 0,
        rotation_mode: str | None = None,
        rotation_optimality_mode: str | None = None,
        rotation_interval_days: int | None = None,
        rotation_interval_minutes: int | None = None,
        rotation_lookback_days: int | None = None,
        rotation_schedule: str | None = None,
        regime_strategy_risk_on_id: int | None = None,
        regime_strategy_neutral_id: int | None = None,
        regime_strategy_risk_off_id: int | None = None,
        overlay_mode: str | None = None,
        overlay_min_tickers: int | None = None,
        overlay_confidence_threshold: float | None = None,
        overlay_watchlist: str | None = None,
        created_at: str,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO unit_rotation_settings (
                unit_id, rotation_enabled, rotation_mode, rotation_optimality_mode,
                rotation_interval_days, rotation_interval_minutes, rotation_lookback_days,
                rotation_schedule, regime_strategy_risk_on_id, regime_strategy_neutral_id,
                regime_strategy_risk_off_id, overlay_mode, overlay_min_tickers,
                overlay_confidence_threshold, overlay_watchlist, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(unit_id) DO UPDATE SET
                rotation_enabled = excluded.rotation_enabled,
                rotation_mode = excluded.rotation_mode,
                rotation_optimality_mode = excluded.rotation_optimality_mode,
                rotation_interval_days = excluded.rotation_interval_days,
                rotation_interval_minutes = excluded.rotation_interval_minutes,
                rotation_lookback_days = excluded.rotation_lookback_days,
                rotation_schedule = excluded.rotation_schedule,
                regime_strategy_risk_on_id = excluded.regime_strategy_risk_on_id,
                regime_strategy_neutral_id = excluded.regime_strategy_neutral_id,
                regime_strategy_risk_off_id = excluded.regime_strategy_risk_off_id,
                overlay_mode = excluded.overlay_mode,
                overlay_min_tickers = excluded.overlay_min_tickers,
                overlay_confidence_threshold = excluded.overlay_confidence_threshold,
                overlay_watchlist = excluded.overlay_watchlist,
                updated_at = excluded.updated_at
            """,
            (
                int(unit_id),
                int(rotation_enabled),
                rotation_mode,
                rotation_optimality_mode,
                rotation_interval_days,
                rotation_interval_minutes,
                rotation_lookback_days,
                rotation_schedule,
                regime_strategy_risk_on_id,
                regime_strategy_neutral_id,
                regime_strategy_risk_off_id,
                overlay_mode,
                overlay_min_tickers,
                overlay_confidence_threshold,
                overlay_watchlist,
                created_at,
                updated_at,
            ),
        )
        self._conn.commit()
