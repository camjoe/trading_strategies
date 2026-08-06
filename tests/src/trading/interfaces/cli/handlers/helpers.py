"""Shared helpers for the CLI handler tests.

Co-located rather than in ``tests/support/`` because only this suite uses them
(see ``tests/support/README.md``). Handlers take a parser so they can call
``parser.error(...)`` on bad input; tests need that to be observable rather than
to exit the process.
"""

from __future__ import annotations

from typing import Any


def fake_parser() -> Any:
    """Return a stand-in parser whose ``error()`` raises ``SystemExit`` with the message.

    ``argparse.ArgumentParser.error`` prints usage to stderr and exits, which
    hides the message being asserted. This raises instead, so a test can match
    on the text with ``pytest.raises(SystemExit)``.
    """

    class _P:
        def error(self, msg: str) -> None:
            raise SystemExit(msg)

    return _P()
