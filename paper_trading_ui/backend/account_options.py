from __future__ import annotations

from trading.domain.rotation import OPTIMALITY_MODES, ROTATION_MODES, ROTATION_OVERLAY_MODES
from trading.services.accounts.config import INSTRUMENT_MODES, OPTION_TYPES, RISK_POLICIES

GOAL_PERIODS = ("monthly", "weekly", "quarterly", "yearly")

_RISK_POLICY_ORDER = ("none", "fixed_stop", "take_profit", "stop_and_target")
_INSTRUMENT_MODE_ORDER = ("equity", "leaps")
_OPTION_TYPE_ORDER = ("call", "put", "both")
_ROTATION_MODE_ORDER = ("time", "optimal", "regime")
_ROTATION_OPTIMALITY_ORDER = ("previous_period_best", "average_return", "hybrid_weighted")
_ROTATION_OVERLAY_ORDER = ("none", "news", "social", "news_social")


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
        "rotationModes": _ordered_values(_ROTATION_MODE_ORDER, ROTATION_MODES),
        "rotationOptimalityModes": _ordered_values(_ROTATION_OPTIMALITY_ORDER, OPTIMALITY_MODES),
        "rotationOverlayModes": _ordered_values(_ROTATION_OVERLAY_ORDER, ROTATION_OVERLAY_MODES),
        "defaults": {
            "goalPeriod": GOAL_PERIODS[0],
            "riskPolicy": _RISK_POLICY_ORDER[0],
            "instrumentMode": _INSTRUMENT_MODE_ORDER[0],
            "rotationMode": _ROTATION_MODE_ORDER[0],
            "rotationOptimalityMode": _ROTATION_OPTIMALITY_ORDER[0],
            "rotationOverlayMode": _ROTATION_OVERLAY_ORDER[0],
        },
    }
