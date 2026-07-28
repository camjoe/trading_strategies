from __future__ import annotations

from datetime import date

import pytest

from trading.backtesting.domain.windowing import add_months


def test_add_months_clips_end_of_month_and_rejects_negative() -> None:
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)

    with pytest.raises(ValueError, match="months must be >= 0"):
        add_months(date(2026, 1, 1), -1)
