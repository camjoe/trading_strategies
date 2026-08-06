"""Shared helpers for the CLI handler tests."""

from __future__ import annotations

from typing import Any


def fake_parser() -> Any:
    """Return a stand-in parser whose ``error()`` raises ``SystemExit`` with the message.

    A real ``ArgumentParser`` prints usage and exits, hiding the message under
    assertion.
    """

    class _P:
        def error(self, msg: str) -> None:
            raise SystemExit(msg)

    return _P()
