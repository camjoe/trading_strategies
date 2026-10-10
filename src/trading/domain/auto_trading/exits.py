"""Risk-based exit detection: positions past their stop-loss or take-profit."""

from typing import Protocol


class PositionCostState(Protocol):
    """Carries per-ticker average cost — all a risk exit needs to price a holding.

    ``AccountState`` and ``BookTradeState`` both satisfy this. Naming either
    concretely would exclude the other, and execution is book-keyed (ADR 010),
    so the only caller passes a book state.

    Declared read-only: a plain annotation would demand a *settable* attribute,
    which a frozen dataclass like ``BookTradeState`` does not offer.
    """

    @property
    def avg_cost(self) -> dict[str, float]: ...


def order_risk_breaches(
    can_sell: list[str],
    prices: dict[str, float],
    state: PositionCostState,
    risk_policy: str,
    stop_loss_pct: float | None,
    take_profit_pct: float | None,
) -> list[str]:
    """Every position past its stop or target, most urgent first.

    Stop-loss breaches come before take-profit breaches; within each group,
    furthest past the threshold first. Ordering is deterministic, so a run's
    exit sequence reproduces from the audit trail.
    """
    if not can_sell:
        return []

    stop_breaches: list[tuple[float, str]] = []
    target_breaches: list[tuple[float, str]] = []
    for ticker in can_sell:
        price = prices.get(ticker)
        avg_cost = state.avg_cost.get(ticker, 0.0)
        if price is None or price <= 0 or avg_cost <= 0:
            continue

        move_pct = ((price / avg_cost) - 1.0) * 100.0
        if risk_policy in {"fixed_stop", "stop_and_target"} and stop_loss_pct is not None:
            if move_pct <= -abs(float(stop_loss_pct)):
                stop_breaches.append((move_pct, ticker))
                continue
        uses_take_profit_policy = risk_policy in {"take_profit", "stop_and_target"}
        if uses_take_profit_policy and take_profit_pct is not None:
            if move_pct >= abs(float(take_profit_pct)):
                target_breaches.append((move_pct, ticker))

    ordered = [ticker for _, ticker in sorted(stop_breaches)]
    ordered.extend(ticker for _, ticker in sorted(target_breaches, reverse=True))
    return list(dict.fromkeys(ordered))
