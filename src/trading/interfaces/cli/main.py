from __future__ import annotations

from infrastructure.database.config import get_db_path
from infrastructure.database.connection import db_session
from infrastructure.market_data.factory import build_provider, resolve_provider_name
from trading.interfaces.cli.commands import build_parser
from trading.interfaces.cli.handlers.context import CliContext
from trading.interfaces.cli.handlers.router import dispatch_command


def _cli_context() -> CliContext:
    # Composition root: one market-data provider per invocation, injected into
    # every flow that reads prices. An optimizer sweep runs a backtest per
    # candidate per window through this one instance, which is what makes the
    # adapter's cumulative call guard mean anything.
    return CliContext(
        db_path=get_db_path(),
        provider=build_provider(),
        provider_name=resolve_provider_name(),
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    with db_session() as conn:
        dispatch_command(conn, args, parser, ctx=_cli_context())


if __name__ == "__main__":
    main()
