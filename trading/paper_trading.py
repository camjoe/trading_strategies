try:
    from trading.accounting import record_trade
    from trading.accounts import create_account, list_accounts, set_benchmark
    from trading.cli import build_parser
    from trading.db import DB_PATH, ensure_db
    from trading.reporting import account_report, compare_strategies, show_snapshots, snapshot_account
except ModuleNotFoundError:
    from accounting import record_trade
    from accounts import create_account, list_accounts, set_benchmark
    from cli import build_parser
    from db import DB_PATH, ensure_db
    from reporting import account_report, compare_strategies, show_snapshots, snapshot_account


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    conn = ensure_db()
    try:
        if args.command == "init":
            print(f"Initialized: {DB_PATH}")

        elif args.command == "create-account":
            create_account(conn, args.name, args.strategy, args.initial_cash, args.benchmark)
            print(
                f"Created account '{args.name}' for strategy '{args.strategy}' "
                f"with benchmark '{args.benchmark.upper()}'."
            )

        elif args.command == "set-benchmark":
            set_benchmark(conn, args.account, args.benchmark)
            print(f"Updated benchmark for '{args.account}' to '{args.benchmark.upper()}'.")

        elif args.command == "list-accounts":
            list_accounts(conn)

        elif args.command == "trade":
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

        elif args.command == "report":
            account_report(conn, args.account)

        elif args.command == "snapshot":
            snapshot_account(conn, args.account, args.time)

        elif args.command == "snapshot-history":
            show_snapshots(conn, args.account, args.limit)

        elif args.command == "compare-strategies":
            compare_strategies(conn, args.lookback)

        else:
            parser.error(f"Unsupported command: {args.command}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
