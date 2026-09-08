"""Portfolio and performance data contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_int

# Sector bucket for symbols missing from the symbol->sector reference data
# (symbol_sectors.json); the rollup degrades gracefully instead of requiring
# full reference coverage.
UNCATEGORIZED_SECTOR = "uncategorized"


# --- Persisted rows ---


@dataclass(frozen=True, slots=True)
class EquitySnapshotRecord:
    """Equity snapshot row (book-keyed storage; account view is the roll-up).

    ``book_id`` and ``id`` are coupled: both are real on a single-book read, and
    both are ``None`` on a multi-book account roll-up row aggregated across books
    (a synthetic aggregate is not an addressable stored row, so it carries no
    id). ``account_id`` is carried by every repository query for consumer
    context.
    """

    id: int | None
    account_id: int
    book_id: int | None
    snapshot_time: str
    cash: float
    market_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> EquitySnapshotRecord:
        return cls(
            id=row_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            book_id=row_int(values, "book_id"),
            snapshot_time=row_expect_str(values, "snapshot_time"),
            cash=row_expect_float(values, "cash"),
            market_value=row_expect_float(values, "market_value"),
            equity=row_expect_float(values, "equity"),
            realized_pnl=row_expect_float(values, "realized_pnl"),
            unrealized_pnl=row_expect_float(values, "unrealized_pnl"),
        )


@dataclass(frozen=True, slots=True)
class DailyMetricRecord:
    """Daily metrics row (book-keyed storage).

    ``account_id`` is carried by every repository query via the books join.
    """

    id: int
    account_id: int
    # NOT NULL in the schema — storage is book-keyed, so every row has one.
    book_id: int
    metric_date: str
    return_pct: float | None
    drawdown_pct: float | None
    turnover_pct: float | None
    slippage_bps: float | None
    hit_rate: float | None
    expectancy: float | None
    risk_adjusted_score: float | None
    trade_count: int | None
    fees_total: float | None
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> DailyMetricRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            book_id=row_expect_int(values, "book_id"),
            metric_date=row_expect_str(values, "metric_date"),
            return_pct=row_float(values, "return_pct"),
            drawdown_pct=row_float(values, "drawdown_pct"),
            turnover_pct=row_float(values, "turnover_pct"),
            slippage_bps=row_float(values, "slippage_bps"),
            hit_rate=row_float(values, "hit_rate"),
            expectancy=row_float(values, "expectancy"),
            risk_adjusted_score=row_float(values, "risk_adjusted_score"),
            trade_count=row_int(values, "trade_count"),
            fees_total=row_float(values, "fees_total"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )


# --- Exposure ---


@dataclass(frozen=True, slots=True)
class AccountExposure:
    """One account's contribution to the cross-account exposure rollup.

    Balance fields come from the account's latest equity snapshot; they are
    None when the account has no snapshots yet (``snapshot_time`` is None in
    that case too). ``position_count`` counts open position rows across the
    account's books and is always populated.
    """

    account_id: int
    account_name: str
    snapshot_time: str | None
    cash: float | None
    market_value: float | None
    equity: float | None
    position_count: int


@dataclass(frozen=True, slots=True)
class PortfolioExposureRollup:
    """Cross-account exposure rollup payload contract.

    ``accounts`` holds one entry per account, ordered by account name.
    Totals sum only the accounts that have at least one equity snapshot
    (``accounts_with_snapshots`` of them), so missing data never reads as
    zero exposure.
    """

    accounts: tuple[AccountExposure, ...]
    accounts_with_snapshots: int
    total_cash: float
    total_market_value: float
    total_equity: float


# --- Concentration ---


@dataclass(frozen=True, slots=True)
class SymbolConcentration:
    """One symbol's cross-account concentration entry.

    ``portfolio_pct`` is the symbol's share of total cross-account market
    value, 0-100. ``account_count`` > 1 means the symbol is held in multiple
    accounts (cross-account overlap). ``sector`` falls back to
    ``UNCATEGORIZED_SECTOR`` for symbols missing from the reference data.
    """

    symbol: str
    sector: str
    market_value: float
    portfolio_pct: float
    account_count: int
    account_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SectorConcentration:
    """One sector's share of total cross-account market value.

    ``portfolio_pct`` is 0-100; symbols missing from the sector reference
    data aggregate under ``UNCATEGORIZED_SECTOR``.
    """

    sector: str
    market_value: float
    portfolio_pct: float
    symbol_count: int


@dataclass(frozen=True, slots=True)
class PortfolioConcentration:
    """Cross-account concentration payload.

    ``symbols`` and ``sectors`` are ordered by market value, largest first.
    Overlap is read from ``symbols`` entries with ``account_count`` > 1.
    Market values come from persisted ``positions`` rows (no live pricing).
    """

    symbols: tuple[SymbolConcentration, ...]
    sectors: tuple[SectorConcentration, ...]
    total_market_value: float
