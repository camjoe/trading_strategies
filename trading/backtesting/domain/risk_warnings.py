from __future__ import annotations

from trading.coercion import row_str


def build_backtest_warnings(account, *, allow_approximate_leaps: bool) -> list[str]:
    warnings: list[str] = [
        "Backtest uses adjusted daily close data only; intraday price path is not modeled.",
        "Universe file may include survivorship bias if it only reflects currently listed symbols.",
    ]

    risk_policy = row_str(account, "risk_policy")
    if risk_policy in {"fixed_stop", "take_profit", "stop_and_target"}:
        warnings.append(
            "Stop-loss/take-profit checks are approximated on daily closes and can differ from intraday execution."
        )

    if row_str(account, "instrument_mode") == "leaps":
        warnings.append(
            "LEAPs mode is approximated using underlying equity prices; "
            "options chain history and Greeks are not modeled."
        )
        if not allow_approximate_leaps:
            warnings.append(
                "LEAPs approximation opt-in was not enabled; proceeding "
                "with approximate LEAPs assumptions for research only."
            )
    return warnings
