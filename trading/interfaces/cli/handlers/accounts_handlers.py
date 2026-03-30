from __future__ import annotations

from typing import Any

from trading.interfaces.cli.handlers.shared import common_account_config_kwargs
from trading.profile_source import get_builtin_profile_preset_path


def _print_profiles_result(prefix: str, created: int, updated: int, skipped: int) -> None:
    print(f"{prefix}created={created}, updated={updated}, skipped={skipped}.")


def handle_init(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    print(f"Initialized: {db_path}")


def handle_create_account(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["create_account"](
        conn,
        args.name,
        args.strategy,
        args.initial_cash,
        args.benchmark,
        config=common_account_config_kwargs(args, include_learning_disabled=False),
    )
    print(
        f"Created account '{args.name}' for strategy '{args.strategy}' "
        f"with benchmark '{args.benchmark.upper()}'."
    )


def handle_configure_account(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    try:
        config = common_account_config_kwargs(args, include_learning_disabled=True)
    except ValueError as error:
        parser.error(str(error))
        return

    deps["configure_account"](
        conn,
        account_name=args.account,
        config=config,
    )
    print(f"Updated account configuration for '{args.account}'.")


def handle_apply_account_profiles(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    profiles = deps["load_account_profiles"](args.file)
    created, updated, skipped = deps["apply_account_profiles"](
        conn,
        profiles,
        create_missing=not args.no_create_missing,
    )
    _print_profiles_result("Applied account profiles: ", created, updated, skipped)


def handle_apply_account_preset(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    preset_file = get_builtin_profile_preset_path(args.preset)
    profiles = deps["load_account_profiles"](str(preset_file))
    created, updated, skipped = deps["apply_account_profiles"](
        conn,
        profiles,
        create_missing=not args.no_create_missing,
    )
    _print_profiles_result(f"Applied preset '{args.preset}': ", created, updated, skipped)


def handle_set_benchmark(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["set_benchmark"](conn, args.account, args.benchmark)
    print(f"Updated benchmark for '{args.account}' to '{args.benchmark.upper()}'.")


def handle_list_accounts(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["list_accounts"](conn)


def handle_trade(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["record_trade"](
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
