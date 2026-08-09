from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

import backtesting.services.simulation as simulation
from backtesting.models import BacktestConfig, RunUniverse
from tests.support.backtesting import bars_from_closes, make_backtest_config

# The service resolves its account through ``get_account``, which returns a typed
# ``AccountRecord``; a namespace stands in for one.
_ACCOUNT = SimpleNamespace(id=1, benchmark_ticker="SPY", initial_cash=1000.0)
_SPEC = SimpleNamespace(indicators=(), required_features=(), strategy_id="trend", default_params={})


def _base_cfg(**overrides) -> BacktestConfig:
    # Frictionless by default: these tests assert exact share counts, which
    # slippage would shift by a share without saying anything about the subject.
    options = {"start": "2026-01-01", "end": "2026-01-03", "slippage_bps": 0.0, "fee_per_trade": 0.0}
    return make_backtest_config("acct", **{**options, **overrides})


@contextmanager
def _patched_service(
    *,
    tickers: list[str],
    resolve_signal_fn=None,
    strategy_spec_fn=None,
    active_strategy_fn=None,
    choose_buy_qty_fn=None,
    insert_run_fn=None,
    insert_trade_fn=None,
    patch_strategy: bool = True,
    dates: tuple[date, date] = (date(2026, 1, 1), date(2026, 1, 3)),
):
    """Stand in for every collaborator ``run_backtest`` resolves for itself.

    The service reaches its account, dates, universe, book, sizing, and writes
    through module-level imports rather than injected callables, so a unit test
    substitutes them here instead of threading them through the call.

    ``patch_strategy=False`` leaves ``resolve_strategy`` and the metrics real, for
    tests whose subject is what a genuine strategy spec does with the bars.
    """
    replacements: dict[str, object] = {
        "get_account": lambda _conn, _name: _ACCOUNT,
        "get_default_book": lambda _conn, *, account_id: None,
        "resolve_run_window": lambda _start, _end, _lookback: dates,
        "resolve_universe": lambda **_kwargs: RunUniverse(
            default_tickers=tickers,
            month_to_tickers={"2026-01": tickers},
            all_tickers=tickers,
            warnings=[],
        ),
        "active_strategy_for_account": active_strategy_fn or (lambda _conn, _account_id: "trend"),
        "insert_run": insert_run_fn or (lambda *_args, **_kwargs: 1),
        "insert_snapshot": lambda *_args, **_kwargs: None,
        "insert_trade": insert_trade_fn or (lambda *_args, **_kwargs: None),
    }
    if patch_strategy:
        replacements["resolve_strategy"] = strategy_spec_fn or (lambda _name: _SPEC)
        replacements["benchmark_return_pct"] = lambda _series, _cash: 1.0
        replacements["max_drawdown_pct"] = lambda _curve: -2.0
    if resolve_signal_fn is not None:
        replacements["evaluate_signal"] = resolve_signal_fn
    if choose_buy_qty_fn is not None:
        replacements["choose_buy_qty"] = choose_buy_qty_fn

    with ExitStack() as stack:
        for target, replacement in replacements.items():
            stack.enter_context(patch.object(simulation, target, replacement))
        yield


def test_simulation_service_rejects_short_history() -> None:
    short_index = pd.date_range("2026-01-01", periods=2, freq="B")

    with pytest.raises(ValueError, match="Need at least 3 trading days"), _patched_service(tickers=["AAPL"]):
        simulation.run_backtest(
            conn=object(),
            cfg=_base_cfg(),
            fetch_bar_history_fn=lambda _tickers, _start, _end: bars_from_closes(
                pd.DataFrame({"AAPL": [100.0, 101.0]}, index=short_index)
            ),
            fetch_benchmark_close_fn=lambda _ticker, _start, _end: pd.Series([100.0, 101.0]),
            persist=False,
        )


def test_simulation_service_returns_result_for_hold_only_run() -> None:
    idx = pd.date_range("2026-01-01", periods=3, freq="B")

    with _patched_service(tickers=["AAPL"], insert_run_fn=lambda *_args, **_kwargs: 77):
        result = simulation.run_backtest(
            conn=SimpleNamespace(commit=lambda: None),
            cfg=_base_cfg(),
            fetch_bar_history_fn=lambda _tickers, _start, _end: bars_from_closes(
                pd.DataFrame({"AAPL": [100.0, 101.0, 102.0]}, index=idx)
            ),
            fetch_benchmark_close_fn=lambda _ticker, _start, _end: pd.Series([100.0, 101.0, 102.0], index=idx),
        )

    assert result.run_id == 77
    assert result.trade_count == 0
    assert result.max_drawdown_pct == -2.0
    assert result.sharpe_ratio is None
    assert result.win_rate_pct is None


def test_simulation_service_strategy_override_bypasses_active_strategy() -> None:
    cfg = _base_cfg()
    cfg.strategy = "  meanrev  "  # whitespace-trimmed override
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    resolved: list[str] = []

    def _active_should_not_run(_conn, _account_id):  # pragma: no cover - must not be called
        raise AssertionError("active_strategy_for_account must not run when strategy override is set")

    with _patched_service(
        tickers=["AAPL"],
        active_strategy_fn=_active_should_not_run,
        strategy_spec_fn=lambda name: (
            resolved.append(name),
            SimpleNamespace(indicators=(), required_features=(), strategy_id=name, default_params={}),
        )[1],
        insert_run_fn=lambda _conn, *, strategy_name, **_kwargs: (resolved.append(f"fk:{strategy_name}"), 88)[1],
    ):
        result = simulation.run_backtest(
            conn=SimpleNamespace(commit=lambda: None),
            cfg=cfg,
            fetch_bar_history_fn=lambda _tickers, _start, _end: bars_from_closes(
                pd.DataFrame({"AAPL": [100.0, 101.0, 102.0]}, index=idx)
            ),
            fetch_benchmark_close_fn=lambda _ticker, _start, _end: pd.Series([100.0, 101.0, 102.0], index=idx),
        )

    assert result.run_id == 88
    # The override (trimmed) drove strategy resolution and the persisted FK.
    assert resolved == ["meanrev", "fk:meanrev"]


# ---------------------------------------------------------------------------
# Buy-path skip guards (require patching evaluate_signal to return "buy")
# ---------------------------------------------------------------------------


def _patched_run_backtest(
    idx: pd.DatetimeIndex,
    close_data: dict,
    resolve_signal_fn,
    choose_buy_qty_fn=None,
    insert_trade_fn=None,
):
    """Run a minimal backtest with all I/O patched; returns BacktestResult.

    The universe is taken from ``close_data`` so multi-ticker bars — where cash
    has to be shared between simultaneous buy signals — can be exercised.
    """
    tickers = list(close_data)
    with _patched_service(
        tickers=tickers,
        resolve_signal_fn=resolve_signal_fn,
        choose_buy_qty_fn=choose_buy_qty_fn,
        insert_trade_fn=insert_trade_fn,
    ):
        return simulation.run_backtest(
            conn=SimpleNamespace(commit=lambda: None),
            cfg=_base_cfg(),
            fetch_bar_history_fn=lambda _tickers, _start, _end: bars_from_closes(pd.DataFrame(close_data, index=idx)),
            fetch_benchmark_close_fn=lambda _ticker, _start, _end: pd.Series([100.0] * len(idx), index=idx),
        )


def test_simulation_service_buy_skip_when_price_is_zero() -> None:
    """Buy signal is ignored when trade price is zero (line 135)."""
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    result = _patched_run_backtest(
        idx,
        {"AAPL": [0.0, 0.0, 0.0]},
        lambda *_args, **_kwargs: "buy",
    )
    assert result.trade_count == 0


def test_simulation_service_buy_skip_when_qty_less_than_one() -> None:
    """Buy signal is ignored when choose_buy_qty returns zero (line 151).

    Also exercises _row_optional_float with a missing key (lines 29-31), since
    the account row does not contain 'trade_size_pct'.
    """
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    result = _patched_run_backtest(
        idx,
        {"AAPL": [100.0, 100.0, 100.0]},
        lambda *_args, **_kwargs: "buy",
        choose_buy_qty_fn=lambda *_args, **_kwargs: 0,
    )
    assert result.trade_count == 0


def test_simulation_service_buy_is_scaled_down_when_required_exceeds_cash() -> None:
    """A request larger than cash is funded down to what cash affords, not dropped.

    Cash-constrained buys are partially filled rather than skipped, so the bar
    spends what it has instead of leaving it idle. ``choose_buy_qty`` already
    caps at available cash in production; this covers the guard behind it.
    """
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    result = _patched_run_backtest(
        idx,
        {"AAPL": [100.0, 100.0, 100.0]},
        lambda *_args, **_kwargs: "buy",
        # 1000 shares × $100 = $100 000, far exceeds the $1 000 starting cash.
        choose_buy_qty_fn=lambda *_args, **_kwargs: 1000,
    )
    assert result.trade_count == 1
    # $1 000 buys 9 shares at $100 plus slippage; never more than cash allows.
    assert result.ending_equity <= 1000.0


# ---------------------------------------------------------------------------
# Sell-path skip guard
# ---------------------------------------------------------------------------


def test_simulation_service_sell_skip_when_price_is_zero() -> None:
    """Sell signal is ignored when trade price is zero after a prior buy (line 184)."""
    idx = pd.date_range("2026-01-01", periods=3, freq="B")

    # Day 1 → buy at 100.0; Day 2 → sell attempt at 0.0 (skipped).
    signals = iter(["buy", "sell"])

    result = _patched_run_backtest(
        idx,
        {"AAPL": [100.0, 100.0, 0.0]},
        lambda *_args, **_kwargs: next(signals, "hold"),
        choose_buy_qty_fn=lambda *_args, **_kwargs: 5,
    )
    # The buy on day 1 executed; the sell on day 2 was skipped.
    assert result.trade_count == 1


# ---------------------------------------------------------------------------
# Warm-up: history before the scoring window initializes indicators, but returns
# and trades are measured only from the window start.
# ---------------------------------------------------------------------------


def _run_with_warmup(*, warmup_months: int, scoring_start: date, end: date, idx, series: pd.Series):
    cfg = _base_cfg(start=scoring_start.isoformat(), end=end.isoformat())
    cfg.strategy = "trend"
    cfg.warmup_months = warmup_months
    frame = pd.DataFrame({"AAPL": series})

    # Realistic fetch: return only the bars within the requested [start, end] range.
    def fetch_bars(_tickers, start, end_):
        return bars_from_closes(frame.loc[pd.Timestamp(start) : pd.Timestamp(end_)])

    # The real trend spec, not a stub: the subject is whether its 30-bar warm-up
    # requirement is met at the scoring-window start.
    with _patched_service(
        tickers=["AAPL"],
        choose_buy_qty_fn=lambda *_args, **_kwargs: 2,
        patch_strategy=False,
        dates=(scoring_start, end),
    ):
        return simulation.run_backtest(
            SimpleNamespace(commit=lambda: None),
            cfg,
            fetch_bar_history_fn=fetch_bars,
            fetch_benchmark_close_fn=lambda _t, _s, _e: pd.Series([100.0] * len(idx), index=idx),
            persist=False,
        )


def test_warmup_enables_signals_in_a_short_window() -> None:
    # A rising series over ~160 business days; the scoring window is only ~21 bars —
    # shorter than the trend strategy's 30-bar warm-up requirement.
    idx = pd.date_range("2026-01-01", periods=160, freq="B")
    series = pd.Series([50.0 + i for i in range(len(idx))], index=idx)
    scoring_start = idx[-21].date()
    end = idx[-1].date()

    cold = _run_with_warmup(warmup_months=0, scoring_start=scoring_start, end=end, idx=idx, series=series)
    warm = _run_with_warmup(warmup_months=3, scoring_start=scoring_start, end=end, idx=idx, series=series)

    # Without warm-up the strategy never accumulates enough history to signal → flat.
    assert cold.trade_count == 0
    assert cold.total_return_pct == 0.0
    # With warm-up it is warm at the window start and trades within the window.
    assert warm.trade_count > 0
    # Either way, the reported period is the scoring window, not the warm-up lead-in.
    assert cold.start_date == scoring_start.isoformat()
    assert warm.start_date == scoring_start.isoformat()


# ---------------------------------------------------------------------------
# Cash allocation across simultaneous buy signals
# ---------------------------------------------------------------------------


def _recorded_trades():
    trades: list[tuple[str, str, float]] = []

    def record(_conn, *, ticker, side, qty, **_kwargs):
        trades.append((ticker, side, qty))

    return trades, record


def test_simultaneous_buys_share_cash_instead_of_funding_alphabetically() -> None:
    """Two equal buy signals, cash for one: both are funded, neither is preferred.

    Funding requests in iteration order would give AAAA its full position and
    ZZZZ nothing — an outcome decided by the alphabet rather than the strategy.
    """
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    trades, record = _recorded_trades()
    _patched_run_backtest(
        idx,
        {"AAAA": [100.0, 100.0, 100.0], "ZZZZ": [100.0, 100.0, 100.0]},
        lambda *_args, **_kwargs: "buy",
        # Each ticker asks for the entire $1 000 of starting cash.
        choose_buy_qty_fn=lambda *_args, **_kwargs: 10,
        insert_trade_fn=record,
    )

    buys = {ticker: qty for ticker, side, qty in trades if side == "buy"}
    assert set(buys) == {"AAAA", "ZZZZ"}
    assert buys["AAAA"] == buys["ZZZZ"]


def test_buy_ordering_does_not_change_the_outcome() -> None:
    """The same signals must allocate identically whichever order they arrive in."""
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    forward, record_forward = _recorded_trades()
    _patched_run_backtest(
        idx,
        {"AAAA": [100.0, 100.0, 100.0], "ZZZZ": [50.0, 50.0, 50.0]},
        lambda *_args, **_kwargs: "buy",
        choose_buy_qty_fn=lambda _cash, price, *_args, **_kwargs: int(800 // price),
        insert_trade_fn=record_forward,
    )
    reverse, record_reverse = _recorded_trades()
    _patched_run_backtest(
        idx,
        {"ZZZZ": [50.0, 50.0, 50.0], "AAAA": [100.0, 100.0, 100.0]},
        lambda *_args, **_kwargs: "buy",
        choose_buy_qty_fn=lambda _cash, price, *_args, **_kwargs: int(800 // price),
        insert_trade_fn=record_reverse,
    )

    assert sorted(forward) == sorted(reverse)


def test_sell_proceeds_fund_the_same_bar_regardless_of_ticker_order() -> None:
    """A sell frees cash for every buy on the bar, not only later tickers.

    ZZZZ is sold and AAAA bought on the same bar; sorted iteration reaches AAAA
    first, so interleaving the two would have hidden ZZZZ's proceeds from it.
    """
    idx = pd.date_range("2026-01-01", periods=4, freq="B")
    trades, record = _recorded_trades()

    def scripted(_strategy, view, _params, _features=None):
        """Buy ZZZZ on the first bar, then swap into AAAA on every later bar.

        The two tickers are priced apart so the signal can tell them apart from
        the bar alone — ``evaluate_signal`` is not given the ticker.
        """
        is_zzzz = view.close() < 75.0
        if view.bars() <= 1:
            return "buy" if is_zzzz else "hold"
        return "sell" if is_zzzz else "buy"

    _patched_run_backtest(
        idx,
        {"AAAA": [100.0] * 4, "ZZZZ": [50.0] * 4},
        scripted,
        # Spend everything available, so AAAA is affordable only once ZZZZ has sold.
        choose_buy_qty_fn=lambda cash, price, *_args, **_kwargs: int(cash // price),
        insert_trade_fn=record,
    )

    assert ("ZZZZ", "buy", 20.0) in trades
    assert any(ticker == "ZZZZ" and side == "sell" for ticker, side, _qty in trades)
    assert any(ticker == "AAAA" and side == "buy" for ticker, side, _qty in trades)


# ---------------------------------------------------------------------------
# Tickers without a price yet
# ---------------------------------------------------------------------------


def test_a_late_listing_ticker_does_not_abort_the_run() -> None:
    """A ticker with no bars yet is skipped until it has a price.

    Days before a ticker's first bar are deliberately empty — the panel will not
    invent a pre-listing price. NaN loses every ordinary comparison, so a bare
    `price <= 0` guard passes it through to sizing, which then fails the whole
    run with "cannot convert float NaN to integer".
    """
    idx = pd.date_range("2026-01-01", periods=5, freq="B")
    closes = pd.DataFrame(
        {"OLD": [10.0] * 5, "NEW": [float("nan"), float("nan"), 50.0, 51.0, 52.0]},
        index=idx,
    )
    frames = bars_from_closes(closes)
    # The provider yields no rows at all before a ticker lists.
    frames["NEW"] = frames["NEW"].dropna()

    trades, record = _recorded_trades()
    # Real sizing on purpose: the crash is inside choose_buy_qty, so a stub that
    # never sees the price would not reproduce it.
    result = _patched_run_backtest_with_frames(
        idx,
        frames,
        ["NEW", "OLD"],
        lambda *_args, **_kwargs: "buy",
        insert_trade_fn=record,
    )

    assert result.trade_count > 0
    # OLD trades from the first bar; NEW is skipped until it has a price of its own.
    assert any(ticker == "OLD" and side == "buy" for ticker, side, _qty in trades)


def _patched_run_backtest_with_frames(
    idx: pd.DatetimeIndex,
    frames: dict,
    tickers: list[str],
    resolve_signal_fn,
    choose_buy_qty_fn=None,
    insert_trade_fn=None,
):
    """Like ``_patched_run_backtest`` but takes pre-built bar frames.

    Lets a test hand tickers genuinely ragged histories, which is the shape that
    produces missing prices in the first place.
    """
    with _patched_service(
        tickers=tickers,
        resolve_signal_fn=resolve_signal_fn,
        choose_buy_qty_fn=choose_buy_qty_fn,
        insert_trade_fn=insert_trade_fn,
        dates=(date(2026, 1, 1), date(2026, 1, 7)),
    ):
        return simulation.run_backtest(
            conn=SimpleNamespace(commit=lambda: None, rollback=lambda: None),
            cfg=_base_cfg(),
            fetch_bar_history_fn=lambda _tickers, _start, _end: frames,
            fetch_benchmark_close_fn=lambda _ticker, _start, _end: pd.Series([100.0] * len(idx), index=idx),
        )


def test_tradeable_price_rejects_missing_and_non_positive_prices() -> None:
    assert simulation._tradeable_price(10.5) == 10.5
    assert simulation._tradeable_price(float("nan")) is None
    assert simulation._tradeable_price(float("inf")) is None
    assert simulation._tradeable_price(0.0) is None
    assert simulation._tradeable_price(-1.0) is None
