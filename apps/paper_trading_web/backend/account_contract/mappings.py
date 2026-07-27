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
    ApiFieldMapping("optionProfitTakePct", "option_profit_take_pct"),
    ApiFieldMapping("optionMaxLossPct", "option_max_loss_pct"),
    ApiFieldMapping("tradeUniverses", "trade_universes"),
    ApiFieldMapping("maxTradesPerRun", "max_trades_per_run"),
)

# The nested `rotation` object (book-owned scheduling, ADR 014); storage names
# match the profile-service `rotation` object keys.
ROTATION_API_FIELDS = (
    ApiFieldMapping("enabled", "enabled"),
    ApiFieldMapping("schedule", "schedule"),
    ApiFieldMapping("lookbackDays", "lookback_days"),
)

TEXT_API_FIELDS = frozenset({"descriptiveName", "optionType"})
