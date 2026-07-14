from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class WeeklyLeaderboardBookPayload:
    book_name: str
    strategy_name: str | None
    avg_return_pct: float | None
    avg_risk_adjusted_score: float | None
    max_drawdown_pct: float | None
    total_trade_count: int
    data_points: int
    rank: int


@dataclass(frozen=True)
class WeeklyLeaderboardAccountPayload:
    account_name: str
    books: list[WeeklyLeaderboardBookPayload]


@dataclass(frozen=True)
class WeeklyLeaderboardArtifactPayload:
    week: str
    generated_at: str
    window_days: int
    accounts: list[WeeklyLeaderboardAccountPayload]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WeeklyPromotionBookPayload:
    book_name: str
    strategy_name: str | None
    book_status: str


@dataclass(frozen=True)
class WeeklyPromotionAccountPayload:
    account_name: str
    ready_for_live: bool
    blockers: list[str]
    books: list[WeeklyPromotionBookPayload]


@dataclass(frozen=True)
class WeeklyPromotionArtifactPayload:
    week: str
    generated_at: str
    accounts: list[WeeklyPromotionAccountPayload]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WeeklyAllocationBookPayload:
    book_name: str
    current_nav: float
    current_pct: float
    target_pct: float
    drift_pct: float
    reweight_suggested: bool


@dataclass(frozen=True)
class WeeklyAllocationAccountPayload:
    account_name: str
    total_nav: float
    books: list[WeeklyAllocationBookPayload]


@dataclass(frozen=True)
class WeeklyAllocationArtifactPayload:
    week: str
    generated_at: str
    drift_threshold_pct: float
    accounts: list[WeeklyAllocationAccountPayload]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)
