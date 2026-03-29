from __future__ import annotations

import pytest

from trading.interfaces.cli.commands import build_parser


def test_requires_command() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])