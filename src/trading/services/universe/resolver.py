"""Universe resolver — resolves named universe identifiers to ticker lists.

Named universes are .txt files stored under ``TRADE_UNIVERSES_DIR``.  A name
maps 1-to-1 to a filename: ``"growth"`` → ``growth.txt``.

Resolution precedence at runtime:
    book-level trade_universes (NOT NULL since revision 0008) > global CLI default
"""

from __future__ import annotations

from common.paths import TRADE_UNIVERSES_DIR
from common.tickers import load_tickers_from_file


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
