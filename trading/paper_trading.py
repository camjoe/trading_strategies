from pathlib import Path
from typing import Callable

try:
    from trading.accounting import record_trade
    from trading.accounts import configure_account, create_account, list_accounts, set_benchmark
    from trading.cli import build_parser
    from trading.db import DB_PATH, ensure_db
    from trading.profiles import apply_account_profiles, load_account_profiles
    from trading.reporting import account_report, compare_strategies, show_snapshots, snapshot_account
except ModuleNotFoundError:
    from accounting import record_trade
    from accounts import configure_account, create_account, list_accounts, set_benchmark
    from cli import build_parser
    from db import DB_PATH, ensure_db
    from profiles import apply_account_profiles, load_account_profiles
    from reporting import account_report, compare_strategies, show_snapshots, snapshot_account


def _common_account_config_kwargs(args, *, include_learning_disabled: bool) -> dict:
    learning_enabled = _resolve_learning_enabled(args, include_learning_disabled)

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


def _resolve_learning_enabled(args, include_learning_disabled: bool) -> bool | None:
    if include_learning_disabled:
        if args.learning_enabled and args.learning_disabled:
            raise ValueError("Use only one of --learning-enabled or --learning-disabled")
        if args.learning_enabled:
            return True
        if args.learning_disabled:
            return False
        return None
    return bool(args.learning_enabled)


def _print_profiles_result(prefix: str, created: int, updated: int, skipped: int) -> None:
    print(f"{prefix}created={created}, updated={updated}, skipped={skipped}.")


def _handle_init(conn, args, parser) -> None:
    print(f"Initialized: {DB_PATH}")


def _handle_create_account(conn, args, parser) -> None:
    create_account(
        conn,
        args.name,
        args.strategy,
        args.initial_cash,
        args.benchmark,
        **_common_account_config_kwargs(args, include_learning_disabled=False),
    )
    print(
        f"Created account '{args.name}' for strategy '{args.strategy}' "
        f"with benchmark '{args.benchmark.upper()}'."
    )


def _handle_configure_account(conn, args, parser) -> None:
    try:
        config_kwargs = _common_account_config_kwargs(args, include_learning_disabled=True)
    except ValueError as error:
        parser.error(str(error))

    configure_account(
        conn,
        account_name=args.account,
        **config_kwargs,
    )
    print(f"Updated account configuration for '{args.account}'.")


def _handle_apply_account_profiles(conn, args, parser) -> None:
    profiles = load_account_profiles(args.file)
    created, updated, skipped = apply_account_profiles(
        conn,
        profiles,
        create_missing=not args.no_create_missing,
    )
    _print_profiles_result("Applied account profiles: ", created, updated, skipped)


def _handle_apply_account_preset(conn, args, parser) -> None:
    preset_file = (
        Path(__file__).resolve().parent
        / "account_profiles"
        / f"{args.preset.strip().lower()}.json"
    )
    profiles = load_account_profiles(str(preset_file))
    created, updated, skipped = apply_account_profiles(
        conn,
        profiles,
        create_missing=not args.no_create_missing,
    )
    _print_profiles_result(f"Applied preset '{args.preset}': ", created, updated, skipped)


def _handle_set_benchmark(conn, args, parser) -> None:
    set_benchmark(conn, args.account, args.benchmark)
    print(f"Updated benchmark for '{args.account}' to '{args.benchmark.upper()}'.")


def _handle_list_accounts(conn, args, parser) -> None:
    list_accounts(conn)


def _handle_trade(conn, args, parser) -> None:
    record_trade(
        conn,
        account_name=args.account,
        side=args.side,
        ticker=args.ticker,
        qty=args.qty,
        price=args.price,
        fee=args.fee,
        trade_time=args.time,
        note=args.note,
    )
    print("Trade recorded.")


def _handle_report(conn, args, parser) -> None:
    account_report(conn, args.account)


def _handle_snapshot(conn, args, parser) -> None:
    snapshot_account(conn, args.account, args.time)


def _handle_snapshot_history(conn, args, parser) -> None:
    show_snapshots(conn, args.account, args.limit)


def _handle_compare_strategies(conn, args, parser) -> None:
    compare_strategies(conn, args.lookback)


COMMAND_HANDLERS: dict[str, Callable] = {
    "init": _handle_init,
    "create-account": _handle_create_account,
    "configure-account": _handle_configure_account,
    "apply-account-profiles": _handle_apply_account_profiles,
    "apply-account-preset": _handle_apply_account_preset,
    "set-benchmark": _handle_set_benchmark,
    "list-accounts": _handle_list_accounts,
    "trade": _handle_trade,
    "report": _handle_report,
    "snapshot": _handle_snapshot,
    "snapshot-history": _handle_snapshot_history,
    "compare-strategies": _handle_compare_strategies,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    conn = ensure_db()
    try:
        command_handler = COMMAND_HANDLERS.get(args.command)
        if command_handler is None:
            parser.error(f"Unsupported command: {args.command}")
        command_handler(conn, args, parser)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
