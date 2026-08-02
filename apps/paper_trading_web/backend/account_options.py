from __future__ import annotations

from trading.services.accounts import (
    INSTRUMENT_MODES,
    OPTION_TYPES,
    RISK_POLICIES,
)

GOAL_PERIODS = ("monthly", "weekly", "quarterly", "yearly")

_RISK_POLICY_ORDER = ("none", "fixed_stop", "take_profit", "stop_and_target")
_INSTRUMENT_MODE_ORDER = ("equity", "leaps")
_OPTION_TYPE_ORDER = ("call", "put", "both")

# Guard against silent drift: every known value must appear in the order tuple.
assert frozenset(_RISK_POLICY_ORDER) == RISK_POLICIES, f"_RISK_POLICY_ORDER out of sync: {RISK_POLICIES}"
assert frozenset(_INSTRUMENT_MODE_ORDER) == INSTRUMENT_MODES, f"_INSTRUMENT_MODE_ORDER out of sync: {INSTRUMENT_MODES}"
assert frozenset(_OPTION_TYPE_ORDER) == OPTION_TYPES, f"_OPTION_TYPE_ORDER out of sync: {OPTION_TYPES}"


def _ordered_values(preferred: tuple[str, ...], allowed: set[str]) -> list[str]:
    ordered = [value for value in preferred if value in allowed]
    extras = sorted(allowed.difference(ordered))
    return ordered + extras


def get_account_config_options() -> dict[str, object]:
    return {
        "goalPeriods": list(GOAL_PERIODS),
        "riskPolicies": _ordered_values(_RISK_POLICY_ORDER, RISK_POLICIES),
        "instrumentModes": _ordered_values(_INSTRUMENT_MODE_ORDER, INSTRUMENT_MODES),
        "optionTypes": _ordered_values(_OPTION_TYPE_ORDER, OPTION_TYPES),
        "defaults": {
            "goalPeriod": GOAL_PERIODS[0],
            "riskPolicy": _RISK_POLICY_ORDER[0],
            "instrumentMode": _INSTRUMENT_MODE_ORDER[0],
        },
    }
