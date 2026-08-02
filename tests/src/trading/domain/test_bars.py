"""Tests for trading.domain.bars — the per-frame bar gap-filling contract.

Both the simulation engine and the live runtime read frames through this rule.
A change here changes what a strategy sees in *both*, which is the point: the
rule exists so the two cannot drift apart.
"""

from __future__ import annotations

import pandas as pd
import pytest

from trading.domain.bars import normalize_bar_frame
from trading.models.market_data import BAR_CLOSE, BAR_COLUMNS, BAR_HIGH, BAR_LOW, BAR_OPEN, BAR_VOLUME


def _frame(index, **columns) -> pd.DataFrame:
    base = {name: [1.0] * len(index) for name in BAR_COLUMNS}
    base.update(columns)
    return pd.DataFrame(base, index=index)


def test_returns_columns_in_contract_order() -> None:
    index = pd.to_datetime(["2024-01-02", "2024-01-03"])
    scrambled = _frame(index)[[BAR_VOLUME, BAR_CLOSE, BAR_LOW, BAR_HIGH, BAR_OPEN]]

    assert list(normalize_bar_frame(scrambled).columns) == list(BAR_COLUMNS)


def test_sorts_an_out_of_order_index() -> None:
    index = pd.to_datetime(["2024-01-04", "2024-01-02", "2024-01-03"])
    result = normalize_bar_frame(_frame(index))

    assert list(result.index) == list(pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]))


def test_prices_carry_forward_but_volume_does_not() -> None:
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    frame = _frame(
        index,
        close=[10.0, float("nan"), 12.0],
        open=[10.0, float("nan"), 12.0],
        high=[10.0, float("nan"), 12.0],
        low=[10.0, float("nan"), 12.0],
        volume=[500.0, float("nan"), 700.0],
    )

    result = normalize_bar_frame(frame)

    # The last trade remains the best estimate of value on an untraded day...
    assert result[BAR_CLOSE].tolist() == [10.0, 10.0, 12.0]
    # ...but repeating its volume would assert trading that never happened.
    assert result[BAR_VOLUME].tolist() == [500.0, 0.0, 700.0]


def test_drops_rows_before_the_first_bar_rather_than_back_filling() -> None:
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    frame = _frame(
        index,
        close=[float("nan"), float("nan"), 12.0],
        open=[float("nan"), float("nan"), 12.0],
        high=[float("nan"), float("nan"), 12.0],
        low=[float("nan"), float("nan"), 12.0],
    )

    result = normalize_bar_frame(frame)

    # Inventing a price that predates the listing would let a strategy trade on it.
    assert list(result.index) == [pd.Timestamp("2024-01-04")]


def test_strips_timezone_without_shifting_the_date() -> None:
    index = pd.to_datetime(["2024-01-02", "2024-01-03"]).tz_localize("US/Eastern")

    result = normalize_bar_frame(_frame(index))

    assert result.index.tz is None
    assert list(result.index) == list(pd.to_datetime(["2024-01-02", "2024-01-03"]))


def test_an_already_naive_index_is_left_alone() -> None:
    index = pd.to_datetime(["2024-01-02", "2024-01-03"])

    result = normalize_bar_frame(_frame(index))

    assert result.index.tz is None
    assert len(result) == 2


def test_a_frame_missing_a_bar_column_is_refused() -> None:
    index = pd.to_datetime(["2024-01-02"])
    frame = _frame(index).drop(columns=[BAR_VOLUME])

    with pytest.raises(KeyError, match=BAR_VOLUME):
        normalize_bar_frame(frame)
