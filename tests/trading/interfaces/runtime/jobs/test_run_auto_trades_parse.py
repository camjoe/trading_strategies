from __future__ import annotations

import sys

import pytest

from tests.support.runtime_jobs import run_auto_trades as module


def test_parse_args_reads_cli_values(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "auto_trader.py",
            "--accounts",
            "acct1,acct2",
            "--tickers-file",
            str(module.DEFAULT_TICKERS_FILE),
            "--min-trades",
            "2",
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
    assert args.tickers_file == module.DEFAULT_TICKERS_FILE
    assert args.min_trades == 2
    assert args.max_trades == 7
    assert args.fee == pytest.approx(1.25)
    assert args.seed == 99
