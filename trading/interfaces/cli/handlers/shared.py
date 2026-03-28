from __future__ import annotations


def resolve_learning_enabled(args, include_learning_disabled: bool) -> bool | None:
    if include_learning_disabled:
        if args.learning_enabled and args.learning_disabled:
            raise ValueError("Use only one of --learning-enabled or --learning-disabled")
        if args.learning_enabled:
            return True
        if args.learning_disabled:
            return False
        return None
    return bool(args.learning_enabled)


def common_account_config_kwargs(args, *, include_learning_disabled: bool) -> dict:
    learning_enabled = resolve_learning_enabled(args, include_learning_disabled)

    return {
        "descriptive_name": args.display_name,
        "goal_min_return_pct": args.goal_min_return_pct,
        "goal_max_return_pct": args.goal_max_return_pct,
        "goal_period": args.goal_period,
        "learning_enabled": learning_enabled,
        "risk_policy": args.risk_policy,
        "stop_loss_pct": args.stop_loss_pct,
        "take_profit_pct": args.take_profit_pct,
        "instrument_mode": args.instrument_mode,
        "option_strike_offset_pct": args.option_strike_offset_pct,
        "option_min_dte": args.option_min_dte,
        "option_max_dte": args.option_max_dte,
        "option_type": args.option_type,
        "target_delta_min": args.target_delta_min,
        "target_delta_max": args.target_delta_max,
        "max_premium_per_trade": args.max_premium_per_trade,
        "max_contracts_per_trade": args.max_contracts_per_trade,
        "iv_rank_min": args.iv_rank_min,
        "iv_rank_max": args.iv_rank_max,
        "roll_dte_threshold": args.roll_dte_threshold,
        "profit_take_pct": args.profit_take_pct,
        "max_loss_pct": args.max_loss_pct,
    }
