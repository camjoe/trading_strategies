from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from trading.backtesting.services.report_service import resolve_signal

from .interpretation import interpret_signal
from .shared import PROVIDER_META, build_unavailable_entry, load_providers

_LOG = logging.getLogger(__name__)


def get_signals(ticker: str) -> list[dict[str, Any]]:
    """Compute feature-only alt-strategy signals for ``ticker``.

    Price history is intentionally omitted in this UI context, so momentum guards
    remain active and ``available`` is always ``False``.
    """
    empty_history = pd.Series([], dtype=float)
    signals: list[dict[str, Any]] = []

    for provider, name, label, strategy_id, _class_name in load_providers():
        meta = PROVIDER_META.get(name, {})
        signal_logic = meta.get("signal_logic", "")
        feature_descriptions = meta.get("feature_descriptions")

        if provider is None:
            unavailable = build_unavailable_entry(name, label)
            signals.append(
                {
                    "strategy": strategy_id,
                    "signal": "hold",
                    "available": False,
                    "features": unavailable["key_scores"],
                    "signal_logic": signal_logic,
                    "feature_descriptions": feature_descriptions,
                    "interpretation": "",
                }
            )
            continue

        try:
            bundle = provider.get_features(ticker)
        except Exception as exc:
            _LOG.warning("features: get_features failed for %s/%s: %s", strategy_id, ticker, exc)
            signals.append(
                {
                    "strategy": strategy_id,
                    "signal": "hold",
                    "available": False,
                    "features": {},
                    "signal_logic": signal_logic,
                    "feature_descriptions": feature_descriptions,
                    "interpretation": "",
                }
            )
            continue

        if not bundle.available:
            signals.append(
                {
                    "strategy": strategy_id,
                    "signal": "hold",
                    "available": False,
                    "features": {},
                    "signal_logic": signal_logic,
                    "feature_descriptions": feature_descriptions,
                    "interpretation": "",
                }
            )
            continue

        try:
            signal = resolve_signal(strategy_id, empty_history, bundle.to_feature_row())
        except Exception as exc:
            _LOG.warning("features: signal fn failed for %s/%s: %s", strategy_id, ticker, exc)
            signal = "hold"

        signals.append(
            {
                "strategy": strategy_id,
                "signal": signal,
                "available": False,
                "reason": "no_price_history",
                "features": bundle.features,
                "signal_logic": signal_logic,
                "feature_descriptions": feature_descriptions,
                "interpretation": interpret_signal(strategy_id, bundle.features),
            }
        )

    return signals
