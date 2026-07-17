from __future__ import annotations

from dataclasses import dataclass


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
