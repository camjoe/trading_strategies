"""Strategy-book data contracts."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from common.coercion import (
    row_expect_float,
    row_expect_int,
    row_expect_str,
    row_float,
    row_int,
    row_str,
)
from common.json_columns import row_json_object

# Which book_rotation_settings upsert wrote a book_rotation_settings_change_events row.
BOOK_ROTATION_SETTINGS_GROUP_SCHEDULING = "scheduling"
BOOK_ROTATION_SETTINGS_GROUP_POLICY = "policy"

# Allowed enum values for the book's execution columns — the vocabulary the
# service layer validates caller input against before a write.
RISK_POLICIES = {"none", "fixed_stop", "take_profit", "stop_and_target"}
INSTRUMENT_MODES = {"equity", "leaps"}
OPTION_TYPES = {"call", "put", "both"}

# Column defaults applied when a book is created without an explicit choice, and
# shown as the fallback when a book row is absent. One home so the create path
# and the display path cannot disagree.
DEFAULT_RISK_POLICY = "none"
DEFAULT_INSTRUMENT_MODE = "equity"


# --- The book itself ---


@dataclass(frozen=True, slots=True)
class BookRecord(Mapping[str, object]):
    """Persisted books row materialized from the database.

    Mapping access mirrors AccountRecord so domain policy functions that take
    a settings mapping (option/leaps knobs are book columns since revision
    0005) accept a book directly.
    """

    id: int
    account_id: int
    name: str
    status: str
    is_default: int
    start_equity: float
    current_cash: float
    current_equity: float
    # NOT NULL since revision 0008 — books are always explicitly set.
    trade_symbols: str
    goal_min_return_pct: float | None
    goal_max_return_pct: float | None
    goal_period: str | None
    # Execution settings are book columns since revision 0004 (roadmap A2).
    learning_enabled: int
    risk_policy: str
    stop_loss_pct: float | None
    take_profit_pct: float | None
    option_profit_take_pct: float | None
    option_max_loss_pct: float | None
    trade_size_pct: float | None
    max_position_pct: float | None
    max_trades_per_run: int | None
    instrument_mode: str
    # Option/leaps settings are book columns since revision 0005 (roadmap A3).
    option_strike_offset_pct: float | None
    option_min_dte: int | None
    option_max_dte: int | None
    option_type: str | None
    target_delta_min: float | None
    target_delta_max: float | None
    max_premium_per_trade: float | None
    max_contracts_per_trade: int | None
    iv_rank_min: float | None
    iv_rank_max: float | None
    roll_dte_threshold: int | None
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> BookRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            name=row_expect_str(values, "name"),
            status=row_expect_str(values, "status"),
            is_default=row_expect_int(values, "is_default"),
            start_equity=row_expect_float(values, "start_equity"),
            current_cash=row_expect_float(values, "current_cash"),
            current_equity=row_expect_float(values, "current_equity"),
            trade_symbols=row_expect_str(values, "trade_symbols"),
            goal_min_return_pct=row_float(values, "goal_min_return_pct"),
            goal_max_return_pct=row_float(values, "goal_max_return_pct"),
            goal_period=row_str(values, "goal_period"),
            learning_enabled=row_expect_int(values, "learning_enabled"),
            risk_policy=row_expect_str(values, "risk_policy"),
            stop_loss_pct=row_float(values, "stop_loss_pct"),
            take_profit_pct=row_float(values, "take_profit_pct"),
            option_profit_take_pct=row_float(values, "option_profit_take_pct"),
            option_max_loss_pct=row_float(values, "option_max_loss_pct"),
            trade_size_pct=row_float(values, "trade_size_pct"),
            max_position_pct=row_float(values, "max_position_pct"),
            max_trades_per_run=row_int(values, "max_trades_per_run"),
            instrument_mode=row_expect_str(values, "instrument_mode"),
            option_strike_offset_pct=row_float(values, "option_strike_offset_pct"),
            option_min_dte=row_int(values, "option_min_dte"),
            option_max_dte=row_int(values, "option_max_dte"),
            option_type=row_str(values, "option_type"),
            target_delta_min=row_float(values, "target_delta_min"),
            target_delta_max=row_float(values, "target_delta_max"),
            max_premium_per_trade=row_float(values, "max_premium_per_trade"),
            max_contracts_per_trade=row_int(values, "max_contracts_per_trade"),
            iv_rank_min=row_float(values, "iv_rank_min"),
            iv_rank_max=row_float(values, "iv_rank_max"),
            roll_dte_threshold=row_int(values, "roll_dte_threshold"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )

    def __getitem__(self, key: str) -> object:
        if key not in self.__dataclass_fields__:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.__dataclass_fields__)

    def __len__(self) -> int:
        return len(self.__dataclass_fields__)

    # --- Strategy assignment ---

    def trade_symbol_list(self) -> list[str]:
        """The book's resolved tickers, decoded from the stored JSON array.

        The one reader of ``trade_symbols``. The run's fetch universe and each
        book's selection universe are both derived from it, and they have to
        agree: a symbol a book can pick is a symbol the run priced. Anything that
        is not a JSON array reads as empty rather than raising — callers decide
        what an empty universe means, and they differ.
        """
        if not self.trade_symbols:
            return []
        decoded = json.loads(self.trade_symbols)
        if not isinstance(decoded, list):
            return []
        return [str(symbol) for symbol in decoded]


@dataclass(frozen=True, slots=True, kw_only=True)
class BookSettingsUpdate:
    """A partial edit to a book's execution, goal, and option columns.

    Field names are the column names: ``BookRepository.update_settings`` builds
    the UPDATE from the fields the caller set. Every field defaults to None,
    meaning "leave this column at its current value" — this path never writes a
    column back to NULL, matching the partial-update contract of ``update``.
    """

    learning_enabled: int | None = None
    risk_policy: str | None = None
    instrument_mode: str | None = None
    option_type: str | None = None
    goal_period: str | None = None
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trade_size_pct: float | None = None
    max_position_pct: float | None = None
    goal_min_return_pct: float | None = None
    goal_max_return_pct: float | None = None
    max_trades_per_run: int | None = None
    option_profit_take_pct: float | None = None
    option_max_loss_pct: float | None = None
    option_strike_offset_pct: float | None = None
    option_min_dte: int | None = None
    option_max_dte: int | None = None
    target_delta_min: float | None = None
    target_delta_max: float | None = None
    max_premium_per_trade: float | None = None
    max_contracts_per_trade: int | None = None
    iv_rank_min: float | None = None
    iv_rank_max: float | None = None
    roll_dte_threshold: int | None = None


@dataclass(frozen=True, slots=True)
class BookAssignmentView:
    """A book's open strategy assignment, resolved for trading-path consumers.

    Carries the catalog-resolved strategy label alongside the raw ids so callers
    (intent generation, rotation, candidate enumeration) do not re-resolve it.
    """

    book_id: int
    strategy_id: int
    strategy_name: str


@dataclass(frozen=True, slots=True)
class BookStrategyAssignmentRecord:
    """Persisted book_strategy_history row materialized from the database.

    The open row (``effective_to is None``) is the book's incumbent assignment;
    closed rows are prior assignments. There is no dedicated incumbent flag —
    "incumbent" is defined by ``effective_to``.
    """

    id: int
    book_id: int
    strategy_id: int
    effective_from: str
    effective_to: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> BookStrategyAssignmentRecord:
        return cls(
            id=row_expect_int(values, "id"),
            book_id=row_expect_int(values, "book_id"),
            strategy_id=row_expect_int(values, "strategy_id"),
            effective_from=row_expect_str(values, "effective_from"),
            effective_to=row_str(values, "effective_to"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )


@dataclass(frozen=True, slots=True)
class TradingBook:
    """A book eligible to trade: active, non-default, with an open strategy assignment."""

    book: BookRecord
    assignment: BookAssignmentView


# --- Rotation settings and decisions ---


@dataclass(frozen=True, slots=True)
class BookRotationSettingsRecord:
    """Persisted book_rotation_settings row materialized from the database.

    Settings only — rotation *state* lives in book_strategy_history (the
    open row) and rotation_decisions history. Rotation uses continuous
    evaluation gated by cooldown (ADR 014).

    The scheduling and policy fields are nullable: None means "use the
    BookRotationScheduleConfig / RotationPolicyConfig code default".
    """

    book_id: int
    rotation_enabled: int
    rotation_lookback_days: int | None
    rotation_schedule: str | None
    min_trades_in_window: int | None
    outperformance_threshold_bps: float | None
    cooldown_days: int | None
    risk_adjusted_return_weight: float | None
    stability_weight: float | None
    drawdown_penalty_weight: float | None
    regime_fit_weight: float | None
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> BookRotationSettingsRecord:
        return cls(
            book_id=row_expect_int(values, "book_id"),
            rotation_enabled=row_expect_int(values, "rotation_enabled"),
            rotation_lookback_days=row_int(values, "rotation_lookback_days"),
            rotation_schedule=row_str(values, "rotation_schedule"),
            min_trades_in_window=row_int(values, "min_trades_in_window"),
            outperformance_threshold_bps=row_float(values, "outperformance_threshold_bps"),
            cooldown_days=row_int(values, "cooldown_days"),
            risk_adjusted_return_weight=row_float(values, "risk_adjusted_return_weight"),
            stability_weight=row_float(values, "stability_weight"),
            drawdown_penalty_weight=row_float(values, "drawdown_penalty_weight"),
            regime_fit_weight=row_float(values, "regime_fit_weight"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )


@dataclass(frozen=True, slots=True)
class BookRotationSettingsChangeEvent:
    """One audited edit to a book_rotation_settings field: prior/new value, when.

    ``changed_fields`` holds only fields whose value actually changed, keyed by
    field name to ``{"old": ..., "new": ...}``.
    """

    id: int
    book_id: int
    settings_group: str
    changed_fields: dict[str, dict[str, object]]
    created_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> BookRotationSettingsChangeEvent:
        return cls(
            id=row_expect_int(values, "id"),
            book_id=row_expect_int(values, "book_id"),
            settings_group=row_expect_str(values, "settings_group"),
            changed_fields=row_json_object(values, "changed_fields"),
            created_at=row_expect_str(values, "created_at"),
        )


@dataclass(frozen=True, slots=True)
class RotationDecisionRecord:
    """Persisted rotation_decisions row materialized from the database.

    Carries the stored strategy-id FKs alongside the catalog-resolved strategy
    labels (``incumbent_strategy``/``challenger_strategy``/``selected_strategy``)
    joined in by the repository's labeled-row read queries, so consumers read
    strategy keys directly without re-resolving.
    """

    id: int
    book_id: int
    decision_time: str
    incumbent_strategy_id: int | None
    challenger_strategy_id: int | None
    selected_strategy_id: int | None
    rotation_action: str
    cooldown_active: int
    score_components_json: str
    gate_results_json: str
    decision_reason: str | None
    config_version: str | None
    created_at: str
    incumbent_strategy: str | None
    challenger_strategy: str | None
    selected_strategy: str | None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> RotationDecisionRecord:
        return cls(
            id=row_expect_int(values, "id"),
            book_id=row_expect_int(values, "book_id"),
            decision_time=row_expect_str(values, "decision_time"),
            incumbent_strategy_id=row_int(values, "incumbent_strategy_id"),
            challenger_strategy_id=row_int(values, "challenger_strategy_id"),
            selected_strategy_id=row_int(values, "selected_strategy_id"),
            rotation_action=row_expect_str(values, "rotation_action"),
            cooldown_active=row_expect_int(values, "cooldown_active"),
            score_components_json=row_expect_str(values, "score_components_json"),
            gate_results_json=row_expect_str(values, "gate_results_json"),
            decision_reason=row_str(values, "decision_reason"),
            config_version=row_str(values, "config_version"),
            created_at=row_expect_str(values, "created_at"),
            incumbent_strategy=row_str(values, "incumbent_strategy"),
            challenger_strategy=row_str(values, "challenger_strategy"),
            selected_strategy=row_str(values, "selected_strategy"),
        )


# --- Holdings and accounting ---


@dataclass(frozen=True, slots=True)
class PositionRecord:
    """Persisted positions row (book-keyed) materialized from the database."""

    book_id: int
    symbol: str
    qty: float
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> PositionRecord:
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
class LedgerEntryRecord:
    """Persisted ledger row (book-keyed) materialized from the database."""

    id: int
    book_id: int
    entry_type: str
    amount: float
    reference_type: str | None
    reference_id: str | None
    entry_time: str
    created_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> LedgerEntryRecord:
        return cls(
            id=row_expect_int(values, "id"),
            book_id=row_expect_int(values, "book_id"),
            entry_type=row_expect_str(values, "entry_type"),
            amount=row_expect_float(values, "amount"),
            reference_type=row_str(values, "reference_type"),
            reference_id=row_str(values, "reference_id"),
            entry_time=row_expect_str(values, "entry_time"),
            created_at=row_expect_str(values, "created_at"),
        )


@dataclass(frozen=True, slots=True)
class BookFillTransition:
    symbol: str
    side: str
    qty: float
    fill_price: float
    commission: float
    requested_price: float | None
    cash_delta: float
    realized_pnl_delta: float
    slippage_amount: float
    ending_qty: float
    ending_avg_cost: float
    ending_cash: float
    ending_realized_pnl: float
    ending_market_value: float
    ending_unrealized_pnl: float
    ending_equity: float


# --- Risk ---


@dataclass(frozen=True, slots=True, kw_only=True)
class RiskDecisionInsert:
    """The risk_decisions columns a caller supplies when creating a row.

    Field names are the column names: `RiskDecisionRepository` builds both the
    INSERT column list and its values from this class.
    """

    account_id: int
    book_id: int | None = None
    decision_time: str
    symbol: str | None = None
    side: str | None = None
    action: str
    reason_code: str
    requested_qty: float | None = None
    approved_qty: float | None = None
    requested_notional: float | None = None
    approved_notional: float | None = None
    risk_payload_json: str = "{}"
    created_at: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RiskDecisionRecord(RiskDecisionInsert):
    """Persisted risk_decisions row materialized from the database.

    The insert payload plus the one column the database owns.
    """

    id: int

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> RiskDecisionRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            book_id=row_int(values, "book_id"),
            decision_time=row_expect_str(values, "decision_time"),
            symbol=row_str(values, "symbol"),
            side=row_str(values, "side"),
            action=row_expect_str(values, "action"),
            reason_code=row_expect_str(values, "reason_code"),
            requested_qty=row_float(values, "requested_qty"),
            approved_qty=row_float(values, "approved_qty"),
            requested_notional=row_float(values, "requested_notional"),
            approved_notional=row_float(values, "approved_notional"),
            risk_payload_json=row_expect_str(values, "risk_payload_json"),
            created_at=row_expect_str(values, "created_at"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RiskSnapshotInsert:
    """The risk_snapshots columns a caller supplies when creating a row.

    Field names are the column names: `RiskSnapshotRepository` builds both the
    INSERT column list and its values from this class.
    """

    account_id: int
    snapshot_time: str
    gross_exposure: float
    net_exposure: float
    max_symbol_concentration_pct: float
    max_sector_concentration_pct: float
    drawdown_pct: float | None = None
    leverage_proxy: float | None = None
    daily_loss_pct: float | None = None
    kill_switch_triggered: int = 0
    risk_payload_json: str = "{}"


@dataclass(frozen=True, slots=True, kw_only=True)
class RiskSnapshotRecord(RiskSnapshotInsert):
    """Persisted risk_snapshots row materialized from the database.

    The insert payload plus the one column the database owns.
    """

    id: int

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> RiskSnapshotRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            snapshot_time=row_expect_str(values, "snapshot_time"),
            gross_exposure=row_expect_float(values, "gross_exposure"),
            net_exposure=row_expect_float(values, "net_exposure"),
            max_symbol_concentration_pct=row_expect_float(values, "max_symbol_concentration_pct"),
            max_sector_concentration_pct=row_expect_float(values, "max_sector_concentration_pct"),
            drawdown_pct=row_float(values, "drawdown_pct"),
            leverage_proxy=row_float(values, "leverage_proxy"),
            daily_loss_pct=row_float(values, "daily_loss_pct"),
            kill_switch_triggered=row_expect_int(values, "kill_switch_triggered"),
            risk_payload_json=row_expect_str(values, "risk_payload_json"),
        )
