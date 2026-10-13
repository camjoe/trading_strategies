from scripts.forge.plans import claimed_status


def test_claimed_status_appends_previous_status() -> None:
    assert claimed_status("feature/x", "drafted") == "in progress (branch `feature/x`). Before pickup: drafted"


def test_claimed_status_without_previous_has_no_trailing_space() -> None:
    assert claimed_status("feature/x", "") == "in progress (branch `feature/x`). Before pickup:"
