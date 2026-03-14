import pytest

from trading.accounts import configure_account, create_account, get_account, list_accounts, set_benchmark


def test_get_account_not_found_raises(conn) -> None:
    with pytest.raises(ValueError, match="Account 'missing' not found"):
        get_account(conn, "missing")


def test_set_benchmark_updates_and_normalizes_ticker(conn) -> None:
    create_account(conn, "acct_bench", "Trend", 1000.0, "spy")

    set_benchmark(conn, "acct_bench", " qqq ")

    account = get_account(conn, "acct_bench")
    assert account["benchmark_ticker"] == "QQQ"


def test_list_accounts_prints_empty_message_when_no_accounts(conn, capsys: pytest.CaptureFixture[str]) -> None:
    list_accounts(conn)

    out = capsys.readouterr().out
    assert "No paper accounts found." in out


@pytest.mark.parametrize(
    ("name", "goal_min", "goal_max", "goal_period", "expected_goal_text"),
    [
        ("acct_goal_none", None, None, "monthly", "goal=not-set"),
        ("acct_goal_range", 1.5, 3.0, "weekly", "goal=1.50% to 3.00% per weekly"),
        ("acct_goal_min", 2.0, None, "monthly", "goal=>= 2.00% per monthly"),
        ("acct_goal_max", None, 4.5, "quarterly", "goal=<= 4.50% per quarterly"),
    ],
)
def test_list_accounts_formats_goal_variants(
    conn,
    capsys: pytest.CaptureFixture[str],
    name: str,
    goal_min: float | None,
    goal_max: float | None,
    goal_period: str,
    expected_goal_text: str,
) -> None:
    create_account(
        conn,
        name=name,
        strategy="Trend",
        initial_cash=5000.0,
        benchmark_ticker="spy",
        goal_min_return_pct=goal_min,
        goal_max_return_pct=goal_max,
        goal_period=goal_period,
    )

    list_accounts(conn)

    out = capsys.readouterr().out
    assert expected_goal_text in out
    assert "benchmark=SPY" in out


@pytest.mark.parametrize(
    ("kwargs", "error_text"),
    [
        ({"initial_cash": 0}, "initial_cash must be greater than 0"),
        ({"risk_policy": "bad"}, "risk_policy must be one of"),
        ({"instrument_mode": "futures"}, "instrument_mode must be one of"),
        ({"goal_min_return_pct": 5, "goal_max_return_pct": 2}, "goal_min_return_pct cannot be greater"),
        ({"option_type": "strangle"}, "option_type must be one of"),
    ],
)
def test_create_account_rejects_invalid_inputs(conn, kwargs: dict[str, object], error_text: str) -> None:
    base_kwargs: dict[str, object] = {
        "name": "acct_bad",
        "strategy": "Trend",
        "initial_cash": 1000.0,
        "benchmark_ticker": "SPY",
    }
    base_kwargs.update(kwargs)

    with pytest.raises(ValueError, match=error_text):
        create_account(conn, **base_kwargs)


@pytest.mark.parametrize(
    ("kwargs", "error_text"),
    [
        ({"target_delta_max": 1.1}, "target_delta_max must be between 0 and 1"),
        ({"option_min_dte": -1}, "option_min_dte must be >= 0"),
        ({"option_max_dte": -1}, "option_max_dte must be >= 0"),
        ({"iv_rank_min": -0.1}, "iv_rank_min must be between 0 and 100"),
        ({"iv_rank_max": 101}, "iv_rank_max must be between 0 and 100"),
    ],
)
def test_create_account_rejects_invalid_option_setting_bounds(
    conn, kwargs: dict[str, object], error_text: str
) -> None:
    base_kwargs: dict[str, object] = {
        "name": "acct_bad_bounds",
        "strategy": "Trend",
        "initial_cash": 1000.0,
        "benchmark_ticker": "SPY",
    }
    base_kwargs.update(kwargs)

    with pytest.raises(ValueError, match=error_text):
        create_account(conn, **base_kwargs)


def test_create_account_normalizes_fields(conn) -> None:
    create_account(
        conn,
        name="acct_norm",
        strategy="Trend",
        initial_cash=2000.0,
        benchmark_ticker=" qqq ",
        descriptive_name="  Growth Focus  ",
        goal_period=" Weekly ",
        option_type="call",
    )

    account = get_account(conn, "acct_norm")
    assert account["benchmark_ticker"] == "QQQ"
    assert account["descriptive_name"] == "Growth Focus"
    assert account["goal_period"] == "weekly"
    assert account["option_type"] == "call"


def test_configure_account_no_fields_is_noop(conn) -> None:
    create_account(conn, "acct_noop", "Trend", 3000.0, "SPY")
    before = dict(get_account(conn, "acct_noop"))

    configure_account(conn, "acct_noop")

    after = dict(get_account(conn, "acct_noop"))
    assert before == after


def test_configure_account_rejects_empty_descriptive_name(conn) -> None:
    create_account(conn, "acct_empty_name", "Trend", 3000.0, "SPY")

    with pytest.raises(ValueError, match="descriptive_name cannot be empty"):
        configure_account(conn, "acct_empty_name", descriptive_name="   ")


def test_configure_account_validates_goal_range_against_existing_values(conn) -> None:
    create_account(
        conn,
        "acct_goal_validate",
        "Trend",
        3000.0,
        "SPY",
        goal_min_return_pct=5.0,
        goal_max_return_pct=10.0,
    )

    with pytest.raises(ValueError, match="goal_min_return_pct cannot be greater than goal_max_return_pct"):
        configure_account(conn, "acct_goal_validate", goal_max_return_pct=4.0)


def test_configure_account_validates_existing_option_settings(conn) -> None:
    create_account(
        conn,
        "acct_opt_validate",
        "Trend",
        3000.0,
        "SPY",
        option_type="call",
        target_delta_min=0.6,
        target_delta_max=0.9,
        iv_rank_min=10.0,
        iv_rank_max=80.0,
    )

    with pytest.raises(ValueError, match="target_delta_min cannot be greater than target_delta_max"):
        configure_account(conn, "acct_opt_validate", target_delta_max=0.5)


@pytest.mark.parametrize(
    ("kwargs", "error_text"),
    [
        ({"risk_policy": "bad_policy"}, "risk_policy must be one of"),
        ({"instrument_mode": "futures"}, "instrument_mode must be one of"),
        ({"option_type": "strangle"}, "option_type must be one of"),
    ],
)
def test_configure_account_rejects_invalid_enum_inputs(
    conn, kwargs: dict[str, object], error_text: str
) -> None:
    create_account(conn, "acct_bad_enum", "Trend", 3000.0, "SPY")

    with pytest.raises(ValueError, match=error_text):
        configure_account(conn, "acct_bad_enum", **kwargs)
