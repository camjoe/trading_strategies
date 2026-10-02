"""Capture a real-history fixture for the scenario bench.

Fetches daily bars for a declared episode through the configured market-data
provider, aligns every ticker onto one common trading calendar, and writes the
frozen CSV under ``local/scenario_bench/``. Operator-run, not part of any runtime
job: the captured bars stay untracked and each machine captures once.

    python -m scripts.data_ops.capture_scenario_fixture --id covid_crash_2020
    python -m scripts.data_ops.capture_scenario_fixture          # all episodes
"""

from __future__ import annotations

import argparse
from datetime import date

import pandas as pd

from backtesting.domain.scenario_bench.fixtures import (
    FIXTURE_DEFINITIONS,
    FixtureDefinition,
    available_fixture_ids,
    fixture_definition,
)
from backtesting.services.scenario_fixtures import save_fixture
from infrastructure.market_data.factory import build_provider
from trading.models.market_data import BAR_COLUMNS
from trading.services.market_data.protocols import MarketDataProvider


def _capture_one(definition: FixtureDefinition, provider: MarketDataProvider) -> None:
    tickers = [*definition.tickers, definition.benchmark]
    frames = provider.fetch_bar_history(
        tickers,
        date.fromisoformat(definition.start),
        date.fromisoformat(definition.end),
    )

    common: pd.Index | None = None
    for frame in frames.values():
        common = frame.index if common is None else common.intersection(frame.index)
    if common is None or len(common) == 0:
        raise SystemExit(f"No common trading days across tickers for {definition.fixture_id}.")

    aligned = {ticker: frames[ticker].loc[common][list(BAR_COLUMNS)] for ticker in tickers}
    path = save_fixture(definition.fixture_id, aligned)
    print(f"Captured {definition.fixture_id}: {len(common)} bars x {len(tickers)} tickers -> {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a real-history fixture for the scenario bench.")
    parser.add_argument("--id", default=None, help="Fixture id to capture (default: all declared fixtures)")
    args = parser.parse_args()

    provider = build_provider()
    definitions = (
        [fixture_definition(args.id)]
        if args.id
        else [FIXTURE_DEFINITIONS[fixture_id] for fixture_id in available_fixture_ids()]
    )
    for definition in definitions:
        _capture_one(definition, provider)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
