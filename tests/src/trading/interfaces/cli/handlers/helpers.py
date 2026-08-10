"""Shared helpers for the CLI handler tests."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import Mock

from trading.interfaces.cli.handlers.context import CliContext


def make_ctx(*, db_path: str = "/data/paper.db", provider: Any = None) -> CliContext:
    """A CliContext carrying only what handlers actually read from it."""
    return CliContext(
        db_path=Path(db_path),
        provider=provider if provider is not None else Mock(),
        provider_name="test-provider",
    )


def patch_services(monkeypatch: Any, module: ModuleType, **fakes: Any) -> None:
    """Replace the services a handler module imported directly.

    Handlers call their services by name rather than looking them up in a
    mapping, so a test substitutes one by rebinding it in the handler module.
    """
    for name, fake in fakes.items():
        monkeypatch.setattr(module, name, fake)


def fake_parser() -> Any:
    """Return a stand-in parser whose ``error()`` raises ``SystemExit`` with the message.

    A real ``ArgumentParser`` prints usage and exits, hiding the message under
    assertion.
    """

    class _P:
        def error(self, msg: str) -> None:
            raise SystemExit(msg)

    return _P()
