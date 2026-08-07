"""Trade-execution data contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from common.coercion import row_expect_float, row_expect_int, row_expect_str

# --- Trade intents ---


@dataclass(frozen=True, slots=True)
class BookTradeCandidate:
    account_id: int
    # The trading book this intent belongs to — the primary key of the flow.
    book_id: int
    strategy_name: str
    side: str
    symbol: str
    qty: int
    requested_price: float
    forced_sell: str | None
    delta_est: float | None
    iv_est: float | None


@dataclass(frozen=True, slots=True)
class BookTradeIntent:
    """A single approved-to-submit trade for one book (the clean-schema execution unit).

    A book is the execution unit for both a plain account's default book and any
    additional books, so this one contract replaces the per-mode selection tuples
    that fed the two legacy submission paths. Passive data only — the execution service maps it to a
    ``BrokerOrder`` and persists the outcome to the clean book-keyed tables.
    """

    book_id: int
    account_id: int
    strategy_id: int | None
    symbol: str
    side: str  # "buy" | "sell"
    qty: float
    requested_price: float | None
    order_type: str = "market"
    time_in_force: str = "day"


@dataclass(frozen=True, slots=True)
class BookTradeState:
    cash: float
    positions: dict[str, float]
    avg_cost: dict[str, float]
    realized_pnl: float = 0.0


# --- Risk gate ---


# Risk limits are layered: the notional cap constrains a single book, and the
# other three constrain one account (the sum of that account's books). Nothing
# here spans accounts — the gate is evaluated per account, so two accounts each
# at their gross limit are not aggregated. Cross-account concentration is
# reported by `services.analysis.concentration` but never gates a trade.

# Default share of *a book's* equity that any single symbol position may occupy.
DEFAULT_MAX_BOOK_NOTIONAL_PCT = 0.25
# Default share of *account* equity that any single symbol may occupy.
DEFAULT_MAX_SYMBOL_CONCENTRATION_PCT = 0.30
# Default cap on gross exposure as a multiple of *account* equity.
DEFAULT_MAX_ACCOUNT_GROSS_EXPOSURE = 1.0
# Default share of *account* equity that any single sector may occupy.
DEFAULT_MAX_SECTOR_CONCENTRATION_PCT = 0.45
# Default distance below peak account equity at which the account stops buying.
# Unlike the four caps above this is a 0-100 percent, matching the signed
# `risk_snapshots.drawdown_pct` it is compared against.
DEFAULT_MAX_DRAWDOWN_PCT = 20.0


@dataclass(frozen=True, slots=True)
class RiskGateConfig:
    # Book-scoped: a fraction of the intent's own book equity.
    max_book_notional_pct: float = DEFAULT_MAX_BOOK_NOTIONAL_PCT
    # Account-scoped: fractions of the account's total equity across its books.
    max_symbol_concentration_pct: float = DEFAULT_MAX_SYMBOL_CONCENTRATION_PCT
    max_account_gross_exposure: float = DEFAULT_MAX_ACCOUNT_GROSS_EXPOSURE
    max_sector_concentration_pct: float = DEFAULT_MAX_SECTOR_CONCENTRATION_PCT
    # Account-scoped loss breaker: blocks buys only, never sells.
    max_drawdown_pct: float = DEFAULT_MAX_DRAWDOWN_PCT
    # Symbol→sector reference data is operator config; the service layer loads it
    # from src/infrastructure/config/symbol_sectors.json and injects it here.
    # An empty map means no sector-concentration limits are applied.
    symbol_sector_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RiskGatePosition:
    """A book position materialized from the database, keyed by (book_id, symbol)."""

    book_id: int
    symbol: str
    qty: float
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> RiskGatePosition:
        return cls(
            book_id=row_expect_int(values, "book_id"),
            symbol=row_expect_str(values, "symbol"),
            qty=row_expect_float(values, "qty"),
            avg_cost=row_expect_float(values, "avg_cost"),
            market_value=row_expect_float(values, "market_value"),
            unrealized_pnl=row_expect_float(values, "unrealized_pnl"),
            updated_at=row_expect_str(values, "updated_at"),
        )


@dataclass(frozen=True, slots=True)
class RiskGateDecision:
    book_id: int
    symbol: str
    side: str
    action: str
    reason_code: str
    requested_qty: int
    approved_qty: int
    requested_notional: float
    approved_notional: float


@dataclass(frozen=True, slots=True)
class RiskGateResult:
    approved_intents: list[BookTradeCandidate]
    decisions: list[RiskGateDecision]
    allowed_count: int
    rescaled_count: int
    blocked_count: int
    gross_exposure_before: float
    gross_exposure_after: float


@dataclass(frozen=True, slots=True)
class GateResult:
    """Outcome of a :class:`~trading.services.execution.gate.PreSubmitGate` evaluation.

    ``approved_intents`` is authoritative for submission — it already contains any
    rescaled intents at their adjusted quantity. ``blocked_intents`` and
    ``rescaled_intents`` are audit views (``rescaled_intents`` is a subset of the
    approved set). ``kill_switch_reasons`` carries any pre-submit halt reasons
    (stale price, reconciliation mismatch, etc.); a non-empty list means the whole
    book is held and nothing is submitted. ``decisions`` are the notional-gate's
    per-intent outcomes (allow/rescale/block + reason codes), bucketed by book;
    callers use them to persist the risk audit. (``RiskGateDecision`` is the
    reused decision contract, bucketed by ``book_id`` under the book-as-bucket
    model.)
    """

    approved_intents: list[BookTradeIntent] = field(default_factory=list)
    blocked_intents: list[BookTradeIntent] = field(default_factory=list)
    rescaled_intents: list[BookTradeIntent] = field(default_factory=list)
    kill_switch_reasons: list[str] = field(default_factory=list)
    decisions: list[RiskGateDecision] = field(default_factory=list)


# --- Submission and NAV ---


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    """Outcome of submitting one book's approved intents through the execution service.

    ``order_ids`` are the clean ``orders`` rows written (one per intent that reached
    the broker). ``kill_switch_reasons`` echoes the gate's reasons plus any
    broker-API anomaly raised mid-loop; a non-empty list means submission halted.
    """

    order_ids: list[int] = field(default_factory=list)
    submitted_count: int = 0
    filled_count: int = 0
    blocked_count: int = 0
    rescaled_count: int = 0
    kill_switch_reasons: list[str] = field(default_factory=list)
    # The global trade throttle stopped this book mid-loop; it applies across
    # the whole run.
    throttled: bool = False


@dataclass(frozen=True, slots=True)
class BookNavMarkResult:
    """Outcome of marking one book's positions to market.

    ``current_equity`` is the re-marked NAV (``current_cash`` + Σ marked position
    value). ``unpriced_symbols`` are positions with no valid live mark, held at
    cost basis (no unrealized P&L) — surfaced so callers can flag a stale book.
    """

    book_id: int
    current_cash: float
    current_equity: float
    unpriced_symbols: list[str] = field(default_factory=list)


@dataclass
class BookRunAudit:
    """Risk audit accumulated across one book run's stages.

    Carries the gate's per-intent decisions plus any block reasons raised later
    in the run (kill switches, the trade throttle, a broker anomaly), the
    run-wide ``kill_switch_reasons``, and the counts rendered into the persisted
    snapshot's ``summary``. Mutable by design: the runtime fills it in as stages
    complete, then hands the whole thing to the execution-owned persistence.
    """

    risk_decisions: list[dict[str, object]] = field(default_factory=list)
    kill_switch_reasons: list[str] = field(default_factory=list)
    blocked_count: int = 0
    rescaled_count: int = 0
    allowed_count: int = 0
    submitted_count: int = 0

    def record_block(self, reason_code: str, *, book_id: int | None = None) -> None:
        """Append a block decision. ``book_id`` is omitted for run-wide reasons."""
        decision: dict[str, object] = {"action": "block", "reason_code": reason_code}
        if book_id is not None:
            decision["book_id"] = book_id
        self.risk_decisions.append(decision)

    def summary(self) -> dict[str, object]:
        return {
            "submitted_count": self.submitted_count,
            "blocked_count": self.blocked_count,
            "rescaled_count": self.rescaled_count,
            "allowed_count": self.allowed_count,
        }


@dataclass(frozen=True, slots=True)
class AccountRunResult:
    """What one account's trading run did, and whether anything stopped it.

    ``submitted_count`` on its own cannot tell a quiet day from a halted one:
    zero trades reads the same whether there were no signals, a kill switch
    blocked every intent before submission, or the broker failed part-way
    through the book loop leaving some books traded and others not. The
    run-wide ``kill_switch_reasons`` travel alongside so the caller can tell
    those apart and set an exit code accordingly.
    """

    account_name: str
    submitted_count: int
    kill_switch_reasons: tuple[str, ...] = ()

    @property
    def halted(self) -> bool:
        """Whether a kill switch stopped this account short of its full intent."""
        return bool(self.kill_switch_reasons)
