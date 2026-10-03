from __future__ import annotations

import sys

import pytest

from tests.src.trading.interfaces.runtime.jobs.loaders import run_auto_trades as module


def test_parse_args_reads_cli_values(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "auto_trader.py",
            "--accounts",
            "acct1,acct2",
            "--tickers-file",
            "custom_universe.txt",
            "--max-trades",
            "7",
            "--fee",
            "1.25",
            "--seed",
            "99",
        ],
    )

    args = module.parse_args()
    assert args.accounts == "acct1,acct2"
    assert args.tickers_file == "custom_universe.txt"
    assert args.max_trades == 7
    assert args.fee == pytest.approx(1.25)
    assert args.seed == 99


def test_parse_args_defaults_tickers_file_to_empty(monkeypatch) -> None:
    """An unset --tickers-file means "derive the universe from the books"."""
    monkeypatch.setattr(sys, "argv", ["auto_trader.py", "--accounts", "acct1"])

    assert module.parse_args().tickers_file == ""
