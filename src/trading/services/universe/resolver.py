"""Universe resolver — expands named universe identifiers into ticker lists.

Named universes are .txt files stored under ``TRADE_UNIVERSES_DIR``.  A name
maps 1-to-1 to a filename: ``"growth"`` → ``growth.txt``.

A name is a **write-time shorthand only**. Books store the resolved tickers
(``books.trade_symbols``, revision 0029), so nothing here runs on the trading
path: editing a universe file changes what future writes resolve to, never what
an existing book is already trading.
"""

from __future__ import annotations

from common.paths import TRADE_UNIVERSES_DIR
from common.tickers import load_tickers_from_file
from trading.domain.exceptions import ValidationError

# The universe a book starts on when a caller names none.
DEFAULT_UNIVERSE_NAME = "default"

# Ticker file for surfaces that take an explicit path rather than book-stored
# symbols: backtests, the strategy lab, benchmark sweeps.
DEFAULT_TICKERS_FILE = str(TRADE_UNIVERSES_DIR / f"{DEFAULT_UNIVERSE_NAME}.txt")


def resolve_named_universes(names: list[str]) -> list[str]:
    """Return a deduplicated union of tickers from all named universe files.

    Args:
        names: Universe identifiers (e.g. ``["default", "growth"]``).

    Returns:
        Ordered, deduplicated list of tickers (first-seen order preserved).

    Raises:
        FileNotFoundError: If any named universe file does not exist.
        ValueError: If *names* is empty.
    """
    if not names:
        raise ValueError("At least one universe name must be provided.")

    seen: dict[str, None] = {}
    for name in names:
        path = TRADE_UNIVERSES_DIR / f"{name}.txt"
        if not path.exists():
            available = ", ".join(list_available_universes()) or "(none)"
            raise FileNotFoundError(f"Universe '{name}' not found at {path}. Available universes: {available}")
        for ticker in load_tickers_from_file(str(path)):
            seen[ticker] = None
    return list(seen)


def list_available_universes() -> list[str]:
    """Return sorted list of universe names available in TRADE_UNIVERSES_DIR."""
    if not TRADE_UNIVERSES_DIR.exists():
        return []
    return sorted(p.stem for p in TRADE_UNIVERSES_DIR.iterdir() if p.suffix == ".txt")


def default_trade_symbols() -> list[str]:
    """Tickers of the universe a book starts on when none is named."""
    return resolve_named_universes([DEFAULT_UNIVERSE_NAME])


def resolve_trade_symbols(names: list[str]) -> list[str]:
    """Expand *names* for storage on a book, as a caller-facing failure.

    The write paths' entry point: an unresolvable name is a bad edit, not an
    internal error, so it surfaces as ``ValidationError`` for the CLI and the
    API to report against the request that carried it.
    """
    try:
        return resolve_named_universes(names)
    except (FileNotFoundError, ValueError) as error:
        raise ValidationError(str(error)) from error
