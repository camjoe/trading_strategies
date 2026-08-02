"""Account data contracts."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, fields

from common.coercion import (
    coerce_bool,
    coerce_float,
    coerce_int,
    coerce_str,
    row_expect_float,
    row_expect_int,
    row_expect_str,
    row_int,
    row_str,
)

# --- Persisted rows and writes ---


@dataclass(frozen=True, slots=True)
class AccountRecord(Mapping[str, object]):
    """Persisted account row materialized from the database.

    The final account shape (revision 0008): identity, custody, and broker
    connection. Strategy truth is book_strategy_history; goals,
    universes, and execution/option settings are books columns.
    """

    id: int
    name: str
    initial_cash: float
    created_at: str
    benchmark_ticker: str
    descriptive_name: str
    broker_type: str | None = None
    broker_host: str | None = None
    broker_port: int | None = None
    broker_client_id: int | None = None
    live_trading_enabled: int | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> AccountRecord:
        return cls(
            id=row_expect_int(values, "id"),
            name=row_expect_str(values, "name"),
            initial_cash=row_expect_float(values, "initial_cash"),
            created_at=row_expect_str(values, "created_at"),
            benchmark_ticker=row_expect_str(values, "benchmark_ticker"),
            descriptive_name=row_expect_str(values, "descriptive_name"),
            broker_type=row_str(values, "broker_type"),
            broker_host=row_str(values, "broker_host"),
            broker_port=row_int(values, "broker_port"),
            broker_client_id=row_int(values, "broker_client_id"),
            live_trading_enabled=row_int(values, "live_trading_enabled"),
        )

    def __getitem__(self, key: str) -> object:
        if key not in self.__dataclass_fields__:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.__dataclass_fields__)

    def __len__(self) -> int:
        return len(self.__dataclass_fields__)


@dataclass(frozen=True, slots=True)
class AccountInsert:
    """Repository-ready create payload after validation, defaults, and normalization."""

    name: str
    initial_cash: float
    created_at: str
    updated_at: str
    benchmark_ticker: str
    descriptive_name: str


# --- Resolved configuration ---


def _coerce_trade_universes(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v).strip().lower() for v in value if str(v).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError(f"trade_universes must be a JSON array, got: {raw!r}")
        return [str(v).strip().lower() for v in parsed if str(v).strip()]
    raise TypeError(f"trade_universes must be a list or JSON string, got {type(value).__name__}")


@dataclass(frozen=True)
class AccountConfig:
    """Caller-facing partial input shared by create_account and configure_account."""

    descriptive_name: str | None = None
    goal_min_return_pct: float | None = None
    goal_max_return_pct: float | None = None
    goal_period: str | None = None
    learning_enabled: bool | None = None
    risk_policy: str | None = None
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trade_size_pct: float | None = None
    max_position_pct: float | None = None
    instrument_mode: str | None = None
    option_strike_offset_pct: float | None = None
    option_min_dte: int | None = None
    option_max_dte: int | None = None
    option_type: str | None = None
    target_delta_min: float | None = None
    target_delta_max: float | None = None
    max_premium_per_trade: float | None = None
    max_contracts_per_trade: int | None = None
    iv_rank_min: float | None = None
    iv_rank_max: float | None = None
    roll_dte_threshold: int | None = None
    option_profit_take_pct: float | None = None
    option_max_loss_pct: float | None = None
    trade_universes: list[str] | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> AccountConfig:
        return cls(
            descriptive_name=coerce_str(values.get("descriptive_name")),
            goal_min_return_pct=coerce_float(values.get("goal_min_return_pct")),
            goal_max_return_pct=coerce_float(values.get("goal_max_return_pct")),
            goal_period=coerce_str(values.get("goal_period")),
            learning_enabled=coerce_bool(values.get("learning_enabled")),
            risk_policy=coerce_str(values.get("risk_policy")),
            stop_loss_pct=coerce_float(values.get("stop_loss_pct")),
            take_profit_pct=coerce_float(values.get("take_profit_pct")),
            trade_size_pct=coerce_float(values.get("trade_size_pct")),
            max_position_pct=coerce_float(values.get("max_position_pct")),
            instrument_mode=coerce_str(values.get("instrument_mode")),
            option_strike_offset_pct=coerce_float(values.get("option_strike_offset_pct")),
            option_min_dte=coerce_int(values.get("option_min_dte")),
            option_max_dte=coerce_int(values.get("option_max_dte")),
            option_type=coerce_str(values.get("option_type")),
            target_delta_min=coerce_float(values.get("target_delta_min")),
            target_delta_max=coerce_float(values.get("target_delta_max")),
            max_premium_per_trade=coerce_float(values.get("max_premium_per_trade")),
            max_contracts_per_trade=coerce_int(values.get("max_contracts_per_trade")),
            iv_rank_min=coerce_float(values.get("iv_rank_min")),
            iv_rank_max=coerce_float(values.get("iv_rank_max")),
            roll_dte_threshold=coerce_int(values.get("roll_dte_threshold")),
            option_profit_take_pct=coerce_float(values.get("option_profit_take_pct")),
            option_max_loss_pct=coerce_float(values.get("option_max_loss_pct")),
            trade_universes=_coerce_trade_universes(values.get("trade_universes")),
        )

    @classmethod
    def has_any_field(cls, values: Mapping[str, object]) -> bool:
        return any(field_name in values for field_name in ACCOUNT_CONFIG_FIELD_NAMES)


ACCOUNT_CONFIG_FIELD_NAMES = tuple(field.name for field in fields(AccountConfig))


# --- Derived views ---


@dataclass
class AccountState:
    """Snapshot of a single account's ledger state after replaying its trade history.

    Produced by :func:`trading.domain.accounting.compute_account_state`.

    Attributes
    ----------
    cash:
        Uninvested cash balance remaining in the account.
    positions:
        Open positions keyed by ticker with share/contract quantity.
    avg_cost:
        Average cost basis per share/contract for each open position.
    realized_pnl:
        Cumulative realised profit/loss from closed trades.
    total_deposited:
        Cumulative cash deposited via settlement-ticker buy trades (e.g. ``CASH``
        buys).  Zero for accounts whose capital is seeded entirely through the
        ``initial_cash`` field rather than deposit trades.  Used as the P&L
        percentage denominator for ``initial_cash = 0`` accounts.
    """

    cash: float
    positions: dict[str, float]
    avg_cost: dict[str, float]
    realized_pnl: float
    # Gross cumulative settlement-ticker deposits; 0.0 unless the deposit model
    # is active (i.e. settlement_ticker is set in compute_account_state).
    # Withdrawals do not reduce this value — it represents total capital invested.
    total_deposited: float = field(default=0.0)


@dataclass(frozen=True)
class AccountDeletionPreview:
    """Compact impact summary shown before an account is deleted."""

    account_name: str
    descriptive_name: str
    strategy: str
