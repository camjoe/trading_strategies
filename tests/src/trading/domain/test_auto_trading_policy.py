from types import SimpleNamespace

import pytest

import trading.domain.auto_trading_policy as auto_trader_policy


def _base_account(**overrides):
    base = {
        "option_strike_offset_pct": 5.0,
        "target_delta_min": None,
        "target_delta_max": None,
        "iv_rank_min": None,
        "iv_rank_max": None,
        "max_contracts_per_trade": None,
        "max_premium_per_trade": None,
        "option_min_dte": 120,
        "option_max_dte": 365,
        "option_type": "call",
        "learning_enabled": 0,
        "risk_policy": "none",
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "instrument_mode": "equity",
        "initial_cash": 5000.0,
        "id": 1,
        "strategy": "trend",
    }
    base.update(overrides)
    return base


def test_choose_qty_helpers() -> None:
    assert auto_trader_policy.choose_buy_qty(cash=10.0, price=11.0, fee=0.0) == 0
    assert auto_trader_policy.choose_buy_qty(cash=100.0, price=10.0, fee=0.0) == 1
    # A sell exits outright, so the whole position goes; sub-share holdings cannot.
    assert auto_trader_policy.closing_sell_qty(position_qty=0.2) == 0
    assert auto_trader_policy.closing_sell_qty(position_qty=9.0) == 9
    assert auto_trader_policy.closing_sell_qty(position_qty=9.7) == 9


def test_choose_buy_qty_respects_custom_trade_and_position_caps() -> None:
    qty = auto_trader_policy.choose_buy_qty(
        cash=10_000.0,
        price=100.0,
        fee=0.0,
        trade_size_pct=12.0,
        max_position_pct=15.0,
        current_position_value=900.0,
        portfolio_equity=10_000.0,
    )
    assert qty == 6


def test_choose_buy_qty_blocks_buys_when_position_cap_is_full() -> None:
    qty = auto_trader_policy.choose_buy_qty(
        cash=10_000.0,
        price=100.0,
        fee=0.0,
        trade_size_pct=10.0,
        max_position_pct=20.0,
        current_position_value=2_000.0,
        portfolio_equity=10_000.0,
    )
    assert qty == 0


def test_estimate_helpers_boundaries() -> None:
    assert auto_trader_policy.estimate_delta(0.0) == pytest.approx(0.55)
    assert auto_trader_policy.estimate_delta(1000.0) == pytest.approx(0.05)
    premium = auto_trader_policy.estimate_option_premium(
        underlying_price=100.0,
        delta_est=0.4,
        min_dte=100,
        max_dte=200,
    )
    assert premium > 0.5


def test_option_candidate_allowed_with_delta_and_iv_filters() -> None:
    account = _base_account(target_delta_min=0.6)
    ok, _, _ = auto_trader_policy.option_candidate_allowed(
        account,
        "AAPL",
        {"AAPL": 50.0},
    )
    assert ok is False

    account = _base_account(iv_rank_min=20.0)
    ok, _, iv_rank = auto_trader_policy.option_candidate_allowed(
        account,
        "AAPL",
        {},
    )
    assert ok is False
    assert iv_rank == -1.0

    account = _base_account(target_delta_min=0.1, target_delta_max=0.9, iv_rank_min=10.0, iv_rank_max=90.0)
    ok, delta, iv_rank = auto_trader_policy.option_candidate_allowed(
        account,
        "AAPL",
        {"AAPL": 50.0},
    )
    assert ok is True
    assert 0.0 <= delta <= 1.0
    assert iv_rank == 50.0


def test_apply_leaps_buy_qty_limits() -> None:
    account = _base_account(max_contracts_per_trade=3, max_premium_per_trade=250.0)
    qty = auto_trader_policy.apply_leaps_buy_qty_limits(qty=5, option_price=100.0, account=account)
    assert qty == 2


def test_build_trade_note_for_leaps_buy() -> None:
    account = _base_account(option_strike_offset_pct=7.5, option_min_dte=90, option_max_dte=180, option_type="put")
    note = auto_trader_policy.build_trade_note(
        learning_enabled=True,
        forced_sell=None,
        risk_policy="none",
        instrument_mode="leaps",
        account=account,
        side="buy",
        delta_est=0.33,
        iv_est=42.0,
        strategy_name="trend",
    )
    assert "selection=heuristic-exploration" in note
    assert "mode=leaps" in note
    assert "delta=0.33" in note
    assert "iv_rank=42.0" in note
    assert "strategy=trend" in note


def test_order_risk_breaches_puts_stop_losses_before_take_profits() -> None:
    """A position bleeding past its stop is more urgent than one past its target."""
    state = SimpleNamespace(avg_cost={"LOSS": 100.0, "WIN": 100.0})
    prices = {"LOSS": 90.0, "WIN": 120.0}

    assert auto_trader_policy.order_risk_breaches(
        can_sell=["WIN", "LOSS"],
        prices=prices,
        state=state,
        risk_policy="stop_and_target",
        stop_loss_pct=5.0,
        take_profit_pct=10.0,
    ) == ["LOSS", "WIN"]


def test_order_risk_breaches_returns_every_breach_worst_first() -> None:
    """Every breach is returned, not one sampled at random."""
    state = SimpleNamespace(avg_cost={"BAD": 100.0, "WORSE": 100.0, "OK": 100.0, "GAIN": 100.0})
    prices = {"BAD": 90.0, "WORSE": 70.0, "OK": 99.0, "GAIN": 130.0}

    assert auto_trader_policy.order_risk_breaches(
        can_sell=["BAD", "OK", "WORSE", "GAIN"],
        prices=prices,
        state=state,
        risk_policy="stop_and_target",
        stop_loss_pct=5.0,
        take_profit_pct=10.0,
    ) == ["WORSE", "BAD", "GAIN"]


def test_order_risk_breaches_is_empty_without_a_breach() -> None:
    state = SimpleNamespace(avg_cost={"FLAT": 100.0})

    assert (
        auto_trader_policy.order_risk_breaches(
            can_sell=["FLAT"],
            prices={"FLAT": 101.0},
            state=state,
            risk_policy="stop_and_target",
            stop_loss_pct=5.0,
            take_profit_pct=10.0,
        )
        == []
    )


def test_allocate_buy_quantities_grants_full_requests_when_cash_covers_them() -> None:
    granted = auto_trader_policy.allocate_buy_quantities(
        [("AAAA", 100.0, 3), ("ZZZZ", 50.0, 4)],
        cash=1000.0,
        fee_per_trade=0.0,
    )
    assert granted == {"AAAA": 3, "ZZZZ": 4}


def test_allocate_buy_quantities_scales_proportionally_when_cash_binds() -> None:
    """Both requests are cut, in proportion to what each asked for."""
    granted = auto_trader_policy.allocate_buy_quantities(
        [("AAAA", 100.0, 10), ("ZZZZ", 100.0, 10)],
        cash=1000.0,
        fee_per_trade=0.0,
    )
    assert granted == {"AAAA": 5, "ZZZZ": 5}


def test_allocate_buy_quantities_is_independent_of_request_order() -> None:
    """The reason this function exists: no ticker may win by sorting first."""
    requests = [("AAAA", 100.0, 6), ("MMMM", 25.0, 8), ("ZZZZ", 50.0, 9)]
    forward = auto_trader_policy.allocate_buy_quantities(requests, cash=700.0, fee_per_trade=1.0)
    reverse = auto_trader_policy.allocate_buy_quantities(list(reversed(requests)), cash=700.0, fee_per_trade=1.0)
    assert forward == reverse


def test_allocate_buy_quantities_never_commits_more_than_available_cash() -> None:
    requests = [("AAAA", 100.0, 10), ("MMMM", 33.0, 10), ("ZZZZ", 7.0, 10)]
    fee = 1.5
    cash = 500.0
    granted = auto_trader_policy.allocate_buy_quantities(requests, cash=cash, fee_per_trade=fee)
    prices = {ticker: price for ticker, price, _qty in requests}
    committed = sum((qty * prices[ticker]) + fee for ticker, qty in granted.items())
    assert committed <= cash


def test_allocate_buy_quantities_drops_tickers_whose_share_cannot_buy_one_share() -> None:
    """A share too small for a single share is skipped rather than rounded up."""
    granted = auto_trader_policy.allocate_buy_quantities(
        [("CHEAP", 1.0, 100), ("PRICEY", 900.0, 1)],
        cash=120.0,
        fee_per_trade=0.0,
    )
    assert "PRICEY" not in granted
    assert granted["CHEAP"] >= 1


def test_allocate_buy_quantities_ignores_unsized_or_unpriced_requests() -> None:
    granted = auto_trader_policy.allocate_buy_quantities(
        [("ZEROQTY", 100.0, 0), ("ZEROPRICE", 0.0, 5), ("GOOD", 10.0, 2)],
        cash=1000.0,
        fee_per_trade=0.0,
    )
    assert granted == {"GOOD": 2}


def test_allocate_buy_quantities_returns_nothing_for_an_empty_bar() -> None:
    assert auto_trader_policy.allocate_buy_quantities([], cash=1000.0, fee_per_trade=0.0) == {}


def test_order_signal_candidates_is_deterministic_for_a_seed() -> None:
    """A decision has to be reproducible from the audit trail, not just observed."""
    candidates = ["AAPL", "MSFT", "NVDA", "AMZN"]
    first = auto_trader_policy.order_signal_candidates(candidates, seed="2026-07-30")
    second = auto_trader_policy.order_signal_candidates(candidates, seed="2026-07-30")
    assert first == second
    assert sorted(first) == sorted(candidates)


def test_order_signal_candidates_ignores_the_order_it_was_given() -> None:
    """Candidates arrive in ticker-file order; that must not survive into the pick."""
    candidates = ["AAPL", "MSFT", "NVDA", "AMZN"]
    forward = auto_trader_policy.order_signal_candidates(candidates, seed="2026-07-30")
    reverse = auto_trader_policy.order_signal_candidates(list(reversed(candidates)), seed="2026-07-30")
    assert forward == reverse


def test_order_signal_candidates_spreads_first_pick_across_names() -> None:
    """The reason this exists: no name may take first pick run after run.

    With a fixed order the first ticker in the universe file was always tried
    first, so every book built its portfolio in file order.
    """
    candidates = ["AAPL", "MSFT", "NVDA", "AMZN"]
    firsts = {
        auto_trader_policy.order_signal_candidates(candidates, seed=f"2026-07-{day:02d}")[0] for day in range(1, 29)
    }
    assert len(firsts) > 1


def test_order_signal_candidates_handles_an_empty_list() -> None:
    assert auto_trader_policy.order_signal_candidates([], seed="2026-07-30") == []


def test_order_capacity_claimants_is_deterministic_for_a_seed() -> None:
    book_ids = [3, 1, 4, 2]
    first = auto_trader_policy.order_capacity_claimants(book_ids, seed="2026-07-30")
    second = auto_trader_policy.order_capacity_claimants(book_ids, seed="2026-07-30")
    assert first == second
    assert sorted(first) == sorted(book_ids)


def test_order_capacity_claimants_ignores_the_order_it_was_given() -> None:
    """Books arrive in id order from the enumeration; that must not survive into the claim."""
    book_ids = [1, 2, 3, 4]
    forward = auto_trader_policy.order_capacity_claimants(book_ids, seed="2026-07-30")
    reverse = auto_trader_policy.order_capacity_claimants(list(reversed(book_ids)), seed="2026-07-30")
    assert forward == reverse


def test_order_capacity_claimants_spreads_first_claim_across_books() -> None:
    """The reason this exists: the lowest book id must not take capacity every run."""
    book_ids = [1, 2, 3, 4]
    firsts = {
        auto_trader_policy.order_capacity_claimants(book_ids, seed=f"2026-07-{day:02d}")[0] for day in range(1, 29)
    }
    assert len(firsts) > 1


def test_order_capacity_claimants_does_not_share_an_order_with_tickers() -> None:
    """The seed is namespaced, so book 1 and a ticker "1" cannot collide."""
    seed = "2026-07-30"
    assert auto_trader_policy.order_capacity_claimants([1, 2, 3, 4], seed=seed) != [
        int(t) for t in auto_trader_policy.order_signal_candidates(["1", "2", "3", "4"], seed=seed)
    ]


def test_order_capacity_claimants_handles_an_empty_list() -> None:
    assert auto_trader_policy.order_capacity_claimants([], seed="2026-07-30") == []
