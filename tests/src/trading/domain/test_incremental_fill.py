from decimal import Decimal

import pytest

from trading.domain.incremental_fill import IncrementalFill, UnpostableFillError, incremental_fill

D = Decimal


def _fill(**overrides):
    args = {
        "reported_qty": D("10"),
        "reported_avg_price": D("105"),
        "reported_commission": D("0"),
        "recorded_qty": D("0"),
        "recorded_notional": D("0"),
        "recorded_commission": D("0"),
    }
    return incremental_fill(**{**args, **overrides})


def test_a_first_report_posts_the_whole_size_at_the_average() -> None:
    assert _fill() == IncrementalFill(qty=D("10"), price=D("105"), commission=D("0"))


def test_a_later_report_prices_only_the_new_shares() -> None:
    result = _fill(recorded_qty=D("5"), recorded_notional=D("500"))

    assert result == IncrementalFill(qty=D("5"), price=D("110"), commission=D("0"))


def test_a_report_matching_the_record_adds_nothing() -> None:
    assert _fill(recorded_qty=D("10"), recorded_notional=D("1050")) is None


def test_commission_is_the_part_not_yet_recorded_and_never_negative() -> None:
    assert _fill(reported_commission=D("1.5"), recorded_commission=D("1")).commission == D("0.5")
    assert _fill(reported_commission=D("0"), recorded_commission=D("1")).commission == D("0")


@pytest.mark.parametrize(
    "overrides",
    [
        {"recorded_qty": D("12"), "recorded_notional": D("1200")},
        {"reported_avg_price": None},
        {"recorded_qty": D("5"), "recorded_notional": D("1100")},
    ],
)
def test_a_report_that_cannot_be_posted_safely_raises(overrides) -> None:
    with pytest.raises(UnpostableFillError):
        _fill(**overrides)
