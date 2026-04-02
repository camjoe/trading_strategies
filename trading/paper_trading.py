# Architecture: compatibility shim — import from canonical location instead:
#   trading.interfaces.cli.main
from trading.interfaces.cli.main import (
    _common_account_config_kwargs,
    _handler_deps,
    _resolve_learning_enabled,
    main,
)

__all__ = [
    "_common_account_config_kwargs",
    "_handler_deps",
    "_resolve_learning_enabled",
    "main",
]

if __name__ == "__main__":
    main()
