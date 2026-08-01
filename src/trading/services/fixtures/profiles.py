"""Named fixture profiles — which synthetic story a generated database tells.

Two profiles share one seeder:

``demo``
    The offline web demo's story. Deliberately small and stable so the demo UI
    and its screenshots stay comparable between runs.

``sandbox``
    A disposable test bed for feature work and code checks. Wider than the demo
    on every axis that costs little to widen: more accounts, non-default books,
    a multi-year history, mid-life cash events, and the settings tables the demo
    leaves empty.

A profile is a declarative description only. It carries no prices and no
quantities-in-shares: the seeder resolves both from the injected market-data
provider at seed time, so a fixture can never quote a price the running system
would not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEMO_PROFILE_NAME = "demo"
SANDBOX_PROFILE_NAME = "sandbox"

# One trading month of history: enough for the demo's charts to have shape
# without making the demo build noticeably slow.
DEMO_BUSINESS_DAYS = 30

# Two trading years. Long enough that trailing-window derivations (the
# risk-adjusted score's rolling window, rotation lookbacks, drawdown history)
# have a full window of real data rather than a warm-up stub.
SANDBOX_BUSINESS_DAYS = 504


@dataclass(frozen=True)
class FixtureBuy:
    """Deploy ``notional`` of cash into ``symbol`` on a business day.

    Sized in cash rather than shares because the share count depends on the
    provider's price for that day, which the profile does not know.
    """

    day_index: int
    symbol: str
    notional: float


@dataclass(frozen=True)
class FixtureSell:
    """Sell ``fraction`` of the position held in ``symbol`` on a business day."""

    day_index: int
    symbol: str
    fraction: float


FixtureTrade = FixtureBuy | FixtureSell


@dataclass(frozen=True)
class FixtureCashEvent:
    """A deposit (positive) or withdrawal (negative) after account creation.

    Opening balances are *not* modelled here. ``accounts.initial_cash`` already
    carries the opening balance and the account-state replay starts from it, so
    an opening deposit row would double-count it.
    """

    day_index: int
    amount: float


@dataclass(frozen=True)
class FixtureBook:
    """A non-default book created beyond the one account creation bootstraps.

    ``opening_cash`` is carved out of the account's ``initial_cash`` rather than
    added on top of it: account-state replay starts from ``initial_cash`` and
    spans every book, so funding a book with new capital would make account cash
    disagree with the sum of its books.
    """

    name: str
    strategy: str
    opening_cash: float
    trades: tuple[FixtureTrade, ...] = ()


@dataclass(frozen=True)
class FixtureRotation:
    """Rotation scheduling for an account's default book."""

    enabled: bool
    challengers: tuple[str, ...]
    lookback_days: int


@dataclass(frozen=True)
class FixtureAccount:
    name: str
    descriptive_name: str
    strategy: str
    initial_cash: float
    benchmark: str
    trade_universes: tuple[str, ...]
    trades: tuple[FixtureTrade, ...] = ()
    cash_events: tuple[FixtureCashEvent, ...] = ()
    extra_books: tuple[FixtureBook, ...] = ()
    rotation: FixtureRotation | None = None


@dataclass(frozen=True)
class FixtureProfile:
    name: str
    business_days: int
    accounts: tuple[FixtureAccount, ...]
    # Provider keys to enable in `feature_providers`. No registered strategy reads
    # these today (the alternative-style primitives were retired), so a row here
    # changes no behaviour — the sandbox seeds one so the table is not left empty,
    # which its coverage gate treats as an unreviewed gap.
    feature_providers: tuple[str, ...] = ()
    # Whether to write the `global_settings` singleton. The demo leaves it unset
    # so it exercises the code-default path.
    seed_global_settings: bool = False
    backtest_accounts: tuple[str, ...] = field(default_factory=tuple)
    promotion_review_accounts: tuple[str, ...] = field(default_factory=tuple)


DEMO_TREND_ACCOUNT = "demo_trend"
DEMO_MOMENTUM_ACCOUNT = "demo_momentum"

# Trade notionals are a fraction of the seeded opening balances, chosen so the
# story leaves meaningful idle cash rather than going all-in.
_DEMO_TREND_POSITION_NOTIONAL = 1_500.0
_DEMO_MOMENTUM_POSITION_NOTIONAL = 1_000.0

DEMO_PROFILE = FixtureProfile(
    name=DEMO_PROFILE_NAME,
    business_days=DEMO_BUSINESS_DAYS,
    accounts=(
        FixtureAccount(
            name=DEMO_TREND_ACCOUNT,
            descriptive_name="Demo Trend",
            strategy="trend",
            initial_cash=10_000.0,
            benchmark="SPY",
            trade_universes=("default",),
            trades=(
                FixtureBuy(day_index=2, symbol="AAPL", notional=_DEMO_TREND_POSITION_NOTIONAL),
                FixtureBuy(day_index=8, symbol="MSFT", notional=_DEMO_TREND_POSITION_NOTIONAL),
                FixtureSell(day_index=20, symbol="AAPL", fraction=0.4),
            ),
        ),
        FixtureAccount(
            name=DEMO_MOMENTUM_ACCOUNT,
            descriptive_name="Demo Momentum",
            strategy="ma_crossover",
            initial_cash=12_000.0,
            benchmark="QQQ",
            trade_universes=("default",),
            trades=(
                FixtureBuy(day_index=4, symbol="NVDA", notional=_DEMO_MOMENTUM_POSITION_NOTIONAL),
                FixtureSell(day_index=16, symbol="NVDA", fraction=0.375),
            ),
        ),
    ),
    backtest_accounts=(DEMO_TREND_ACCOUNT,),
    promotion_review_accounts=(DEMO_TREND_ACCOUNT,),
)


SANDBOX_CORE_ACCOUNT = "sandbox_core"
SANDBOX_MULTI_BOOK_ACCOUNT = "sandbox_multi_book"
SANDBOX_ROTATION_ACCOUNT = "sandbox_rotation"
SANDBOX_IDLE_ACCOUNT = "sandbox_idle"

# Sandbox trades are spread across the two-year window so trailing derivations
# see both active and quiet stretches rather than one clustered burst.
_SANDBOX_POSITION_NOTIONAL = 4_000.0
_SANDBOX_SMALL_POSITION_NOTIONAL = 2_500.0

# Capital carved out of the parent account for each non-default sleeve book.
_SANDBOX_SLEEVE_OPENING_CASH = 12_000.0

# A mid-life deposit and withdrawal, the only way `ledger` cash events and a
# non-zero `total_deposited` appear in a generated database.
_SANDBOX_DEPOSIT = 15_000.0
_SANDBOX_WITHDRAWAL = -4_000.0

# Rotation evaluates challengers over a trailing window; one trading quarter is
# long enough to score against without spanning the whole history.
_SANDBOX_ROTATION_LOOKBACK_DAYS = 63

SANDBOX_PROFILE = FixtureProfile(
    name=SANDBOX_PROFILE_NAME,
    business_days=SANDBOX_BUSINESS_DAYS,
    accounts=(
        FixtureAccount(
            name=SANDBOX_CORE_ACCOUNT,
            descriptive_name="Sandbox Core",
            strategy="trend",
            initial_cash=50_000.0,
            benchmark="SPY",
            trade_universes=("default",),
            trades=(
                FixtureBuy(day_index=5, symbol="AAPL", notional=_SANDBOX_POSITION_NOTIONAL),
                FixtureBuy(day_index=40, symbol="MSFT", notional=_SANDBOX_POSITION_NOTIONAL),
                FixtureSell(day_index=120, symbol="AAPL", fraction=0.5),
                FixtureBuy(day_index=200, symbol="NVDA", notional=_SANDBOX_POSITION_NOTIONAL),
                FixtureSell(day_index=310, symbol="MSFT", fraction=1.0),
                FixtureBuy(day_index=400, symbol="JPM", notional=_SANDBOX_SMALL_POSITION_NOTIONAL),
                FixtureSell(day_index=470, symbol="NVDA", fraction=0.25),
            ),
            cash_events=(
                FixtureCashEvent(day_index=150, amount=_SANDBOX_DEPOSIT),
                FixtureCashEvent(day_index=380, amount=_SANDBOX_WITHDRAWAL),
            ),
        ),
        FixtureAccount(
            name=SANDBOX_MULTI_BOOK_ACCOUNT,
            descriptive_name="Sandbox Multi-Book",
            strategy="rsi",
            initial_cash=40_000.0,
            benchmark="SPY",
            trade_universes=("large_cap",),
            trades=(
                FixtureBuy(day_index=12, symbol="WMT", notional=_SANDBOX_SMALL_POSITION_NOTIONAL),
                FixtureSell(day_index=260, symbol="WMT", fraction=0.6),
            ),
            extra_books=(
                FixtureBook(
                    name="growth_sleeve",
                    strategy="breakout",
                    opening_cash=_SANDBOX_SLEEVE_OPENING_CASH,
                    trades=(
                        FixtureBuy(day_index=30, symbol="TSLA", notional=_SANDBOX_SMALL_POSITION_NOTIONAL),
                        FixtureSell(day_index=180, symbol="TSLA", fraction=0.5),
                        FixtureBuy(day_index=350, symbol="META", notional=_SANDBOX_SMALL_POSITION_NOTIONAL),
                    ),
                ),
                FixtureBook(
                    name="defensive_sleeve",
                    strategy="mean_reversion",
                    opening_cash=_SANDBOX_SLEEVE_OPENING_CASH,
                    trades=(
                        FixtureBuy(day_index=60, symbol="JNJ", notional=_SANDBOX_SMALL_POSITION_NOTIONAL),
                        FixtureSell(day_index=420, symbol="JNJ", fraction=1.0),
                    ),
                ),
            ),
        ),
        FixtureAccount(
            name=SANDBOX_ROTATION_ACCOUNT,
            descriptive_name="Sandbox Rotation",
            strategy="ma_crossover",
            initial_cash=25_000.0,
            benchmark="QQQ",
            trade_universes=("growth",),
            trades=(
                FixtureBuy(day_index=20, symbol="GOOGL", notional=_SANDBOX_SMALL_POSITION_NOTIONAL),
                FixtureSell(day_index=290, symbol="GOOGL", fraction=0.75),
            ),
            rotation=FixtureRotation(
                enabled=True,
                challengers=("rsi", "breakout"),
                lookback_days=_SANDBOX_ROTATION_LOOKBACK_DAYS,
            ),
        ),
        # An account that was created and never traded. Empty-state rendering and
        # "no data yet" branches are a real code path worth having in the bed.
        FixtureAccount(
            name=SANDBOX_IDLE_ACCOUNT,
            descriptive_name="Sandbox Idle",
            strategy="bollinger_mean_reversion",
            initial_cash=10_000.0,
            benchmark="SPY",
            trade_universes=("default",),
        ),
    ),
    # Named for the provider, not for a strategy: the previous value here was
    # "news_sentiment", a strategy id that no longer resolves.
    feature_providers=("news",),
    seed_global_settings=True,
    backtest_accounts=(SANDBOX_CORE_ACCOUNT, SANDBOX_ROTATION_ACCOUNT),
    promotion_review_accounts=(SANDBOX_CORE_ACCOUNT, SANDBOX_ROTATION_ACCOUNT),
)


PROFILES: dict[str, FixtureProfile] = {
    DEMO_PROFILE.name: DEMO_PROFILE,
    SANDBOX_PROFILE.name: SANDBOX_PROFILE,
}


def resolve_profile(name: str) -> FixtureProfile:
    """Look up a profile by name, erroring with the valid set when unknown."""
    profile = PROFILES.get(name.strip().lower())
    if profile is None:
        raise ValueError(f"Unknown fixture profile '{name}'. Available: {', '.join(sorted(PROFILES))}")
    return profile
