from __future__ import annotations


def build_backtest_warnings(
    *,
    risk_policy: str | None,
    instrument_mode: str | None,
    allow_approximate_leaps: bool,
) -> list[str]:
    """Assemble the standard backtest caveats from the execution settings.

    Execution settings are book-owned (revision 0004); callers pass the
    default book's values.
    """
    warnings: list[str] = [
        "Backtest uses adjusted daily close data only; intraday price path is not modeled.",
        "Universe file may include survivorship bias if it only reflects currently listed symbols.",
    ]

    if risk_policy in {"fixed_stop", "take_profit", "stop_and_target"}:
        warnings.append(
            "Stop-loss/take-profit checks are approximated on daily closes and can differ from intraday execution."
        )

    if instrument_mode == "leaps":
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
