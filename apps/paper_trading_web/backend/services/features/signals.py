from __future__ import annotations

import logging
from typing import Any

from .interpretation import interpret_signal
from .shared import PROVIDER_META, build_unavailable_entry, load_providers

_LOG = logging.getLogger(__name__)


def get_signals(ticker: str) -> list[dict[str, Any]]:
    """Report each external provider's features for ``ticker``.

    The signal is always ``"hold"``: the feature-gated strategy primitives were
    retired, so nothing consumes these features and there is no signal to
    compute. The providers still run, so the panel keeps showing what they see.
    """
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

        # No strategy consumes these features since the feature-gated primitives
        # were retired, so there is no signal to compute — the panel shows the
        # provider's feature values and says so. Restoring a strategy that
        # declares required_features is what makes this meaningful again.
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
