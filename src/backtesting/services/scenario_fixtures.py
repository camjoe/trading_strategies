"""Read and write frozen scenario-bench fixtures under ``local/scenario_bench/``.

A fixture is one CSV in long format (``ticker,date,open,high,low,close,volume``),
holding real daily bars captured once for a real-history episode. The bars are not
tracked in the repository, so this is the only reader/writer and it lives on the
untracked path.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from common.paths import LOCAL_DIR
from trading.domain.exceptions import ValidationError
from trading.models.market_data import BAR_COLUMNS

SCENARIO_BENCH_FIXTURES_DIR = LOCAL_DIR / "scenario_bench"

_DATE_COLUMN = "date"
_TICKER_COLUMN = "ticker"


def fixture_path(fixture_id: str) -> Path:
    return SCENARIO_BENCH_FIXTURES_DIR / f"{fixture_id}.csv"


def save_fixture(fixture_id: str, frames: dict[str, pd.DataFrame]) -> Path:
    """Write per-ticker bar frames to the fixture's CSV and return its path."""
    if not frames:
        raise ValidationError("A fixture needs at least one ticker frame.")

    tidy_frames: list[pd.DataFrame] = []
    for ticker, frame in frames.items():
        tidy = frame[list(BAR_COLUMNS)].reset_index()
        tidy.columns = [_DATE_COLUMN, *BAR_COLUMNS]
        tidy.insert(0, _TICKER_COLUMN, ticker)
        tidy_frames.append(tidy)

    combined = pd.concat(tidy_frames, ignore_index=True)
    path = fixture_path(fixture_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(path, index=False)
    return path


def load_fixture(fixture_id: str) -> dict[str, pd.DataFrame]:
    """Read a fixture into one date-indexed bar frame per ticker.

    Raises if the fixture is missing, because a real-data scenario cannot run
    without it. Capture it with ``scripts.data_ops.capture_scenario_fixture``.
    """
    path = fixture_path(fixture_id)
    if not path.exists():
        raise ValidationError(
            f"Scenario fixture not found: {path}. "
            f"Capture it with: python -m scripts.data_ops.capture_scenario_fixture --id {fixture_id}"
        )

    raw = pd.read_csv(path, parse_dates=[_DATE_COLUMN])
    frames: dict[str, pd.DataFrame] = {}
    for ticker, group in raw.groupby(_TICKER_COLUMN):
        frame = group.set_index(_DATE_COLUMN)[list(BAR_COLUMNS)].sort_index()
        frames[str(ticker)] = frame
    return frames
