from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel

from trading.models import AccountConfig


@dataclass(frozen=True)
class ApiFieldMapping:
    api_name: str
    storage_name: str


@dataclass(frozen=True)
class AdminCreateAccountCommand:
    name: str
    strategy: str
    initial_cash: float
    benchmark_ticker: str
    config_values: dict[str, object]
    rotation_profile: dict[str, object]

    @property
    def config(self) -> AccountConfig:
        return AccountConfig.from_mapping(self.config_values)


@dataclass(frozen=True)
class AccountParamsUpdateCommand:
    strategy: str | None
    config_values: dict[str, object]
    rotation_profile: dict[str, object]

    @property
    def config(self) -> AccountConfig:
        return AccountConfig.from_mapping(self.config_values)


ACCOUNT_CONFIG_API_FIELDS = (
    ApiFieldMapping("descriptiveName", "descriptive_name"),
    ApiFieldMapping("goalMinReturnPct", "goal_min_return_pct"),
    ApiFieldMapping("goalMaxReturnPct", "goal_max_return_pct"),
    ApiFieldMapping("goalPeriod", "goal_period"),
    ApiFieldMapping("learningEnabled", "learning_enabled"),
    ApiFieldMapping("riskPolicy", "risk_policy"),
    ApiFieldMapping("stopLossPct", "stop_loss_pct"),
    ApiFieldMapping("takeProfitPct", "take_profit_pct"),
    ApiFieldMapping("tradeSizePct", "trade_size_pct"),
    ApiFieldMapping("maxPositionPct", "max_position_pct"),
    ApiFieldMapping("instrumentMode", "instrument_mode"),
    ApiFieldMapping("optionStrikeOffsetPct", "option_strike_offset_pct"),
    ApiFieldMapping("optionMinDte", "option_min_dte"),
    ApiFieldMapping("optionMaxDte", "option_max_dte"),
    ApiFieldMapping("optionType", "option_type"),
    ApiFieldMapping("targetDeltaMin", "target_delta_min"),
    ApiFieldMapping("targetDeltaMax", "target_delta_max"),
    ApiFieldMapping("maxPremiumPerTrade", "max_premium_per_trade"),
    ApiFieldMapping("maxContractsPerTrade", "max_contracts_per_trade"),
    ApiFieldMapping("ivRankMin", "iv_rank_min"),
    ApiFieldMapping("ivRankMax", "iv_rank_max"),
    ApiFieldMapping("rollDteThreshold", "roll_dte_threshold"),
    ApiFieldMapping("profitTakePct", "profit_take_pct"),
    ApiFieldMapping("maxLossPct", "max_loss_pct"),
)

ROTATION_API_FIELDS = (
    ApiFieldMapping("rotationEnabled", "rotation_enabled"),
    ApiFieldMapping("rotationMode", "rotation_mode"),
    ApiFieldMapping("rotationOptimalityMode", "rotation_optimality_mode"),
    ApiFieldMapping("rotationIntervalDays", "rotation_interval_days"),
    ApiFieldMapping("rotationIntervalMinutes", "rotation_interval_minutes"),
    ApiFieldMapping("rotationLookbackDays", "rotation_lookback_days"),
    ApiFieldMapping("rotationSchedule", "rotation_schedule"),
    ApiFieldMapping("rotationRegimeStrategyRiskOn", "rotation_regime_strategy_risk_on"),
    ApiFieldMapping("rotationRegimeStrategyNeutral", "rotation_regime_strategy_neutral"),
    ApiFieldMapping("rotationRegimeStrategyRiskOff", "rotation_regime_strategy_risk_off"),
    ApiFieldMapping("rotationOverlayMode", "rotation_overlay_mode"),
    ApiFieldMapping("rotationOverlayMinTickers", "rotation_overlay_min_tickers"),
    ApiFieldMapping("rotationOverlayConfidenceThreshold", "rotation_overlay_confidence_threshold"),
    ApiFieldMapping("rotationOverlayWatchlist", "rotation_overlay_watchlist"),
    ApiFieldMapping("rotationActiveIndex", "rotation_active_index"),
    ApiFieldMapping("rotationLastAt", "rotation_last_at"),
    ApiFieldMapping("rotationActiveStrategy", "rotation_active_strategy"),
)

_TEXT_API_FIELDS = frozenset({"descriptiveName", "optionType"})


def _clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value))


def _dump_model(model: BaseModel, *, exclude_none: bool) -> dict[str, object]:
    return dict(model.model_dump(exclude_none=exclude_none))


def _map_api_values(
    values: Mapping[str, object],
    field_mappings: tuple[ApiFieldMapping, ...],
) -> dict[str, object]:
    mapped: dict[str, object] = {}
    for field in field_mappings:
        if field.api_name not in values:
            continue
        value = values[field.api_name]
        if field.api_name in _TEXT_API_FIELDS:
            value = _clean_text(value)
        mapped[field.storage_name] = value
    return mapped


def build_admin_create_account_command(payload: BaseModel) -> AdminCreateAccountCommand:
    values = _dump_model(payload, exclude_none=True)
    return AdminCreateAccountCommand(
        name=str(values["name"]).strip(),
        strategy=str(values["strategy"]).strip(),
        initial_cash=_coerce_float(values["initialCash"]),
        benchmark_ticker=str(values.get("benchmarkTicker", "SPY")).strip().upper() or "SPY",
        config_values=_map_api_values(values, ACCOUNT_CONFIG_API_FIELDS),
        rotation_profile=_map_api_values(values, ROTATION_API_FIELDS),
    )


def build_account_params_update_command(body: BaseModel) -> AccountParamsUpdateCommand:
    values = _dump_model(body, exclude_none=True)
    strategy_value = values.get("strategy")
    return AccountParamsUpdateCommand(
        strategy=_clean_text(strategy_value) if strategy_value is not None else None,
        config_values=_map_api_values(values, ACCOUNT_CONFIG_API_FIELDS),
        rotation_profile=_map_api_values(values, ROTATION_API_FIELDS),
    )
