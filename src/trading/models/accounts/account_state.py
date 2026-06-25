from __future__ import annotations

from dataclasses import dataclass, field


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
