from __future__ import annotations

from trading.interfaces.cli.handlers.context import CliContext
from trading.interfaces.cli.handlers.shared import common_account_config_kwargs
from trading.services.accounts.listing import fetch_account_listing_lines
from trading.services.accounts.mutations import configure_account, create_account, set_benchmark
from trading.services.execution.ledger.mutations import record_trade


def handle_init(conn, args, parser, *, ctx: CliContext) -> None:
    print(f"Initialized: {ctx.db_path}")


def handle_create_account(conn, args, parser, *, ctx: CliContext) -> None:
    try:
        create_account(
            conn,
            args.name,
            args.strategy,
            args.initial_cash,
            args.benchmark,
            config=common_account_config_kwargs(args, include_learning_disabled=False),
        )
    except ValueError as error:
        parser.error(str(error))
        return
    print(f"Created account '{args.name}' for strategy '{args.strategy}' with benchmark '{args.benchmark.upper()}'.")


def handle_configure_account(conn, args, parser, *, ctx: CliContext) -> None:
    try:
        config = common_account_config_kwargs(args, include_learning_disabled=True)
    except ValueError as error:
        parser.error(str(error))
        return

    configure_account(
        conn,
        account_name=args.account,
        config=config,
    )
    print(f"Updated account configuration for '{args.account}'.")


def handle_set_benchmark(conn, args, parser, *, ctx: CliContext) -> None:
    set_benchmark(conn, args.account, args.benchmark)
    print(f"Updated benchmark for '{args.account}' to '{args.benchmark.upper()}'.")


def handle_list_accounts(conn, args, parser, *, ctx: CliContext) -> None:
    lines = fetch_account_listing_lines(conn)
    if not lines:
        print("No accounts found.")
        return
    for line in lines:
        print(line)


def handle_trade(conn, args, parser, *, ctx: CliContext) -> None:
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
