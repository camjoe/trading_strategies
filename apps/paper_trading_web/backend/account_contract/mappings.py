from __future__ import annotations

from .models import ApiFieldMapping

ACCOUNT_CONFIG_API_FIELDS = (
    ApiFieldMapping("accountKind", "account_kind"),
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

TEXT_API_FIELDS = frozenset({"descriptiveName", "optionType"})
