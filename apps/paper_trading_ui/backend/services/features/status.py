from __future__ import annotations

import logging
from typing import Any

from .shared import (
    HEALTH_PROBE_TICKER,
    PROVIDER_META,
    build_unavailable_entry,
    load_providers,
)

_LOG = logging.getLogger(__name__)


def get_provider_status() -> list[dict[str, Any]]:
    """Probe all three alt-strategy feature providers and return their status.

    Uses ``SPY`` as the health-probe ticker. Each entry includes provider metadata
    so the frontend can render explanatory cards in one response.
    """
    results: list[dict[str, Any]] = []
    for provider, name, label, _strategy_id, _class_name in load_providers():
        if provider is None:
            results.append(build_unavailable_entry(name, label))
            continue
        meta = PROVIDER_META.get(name, {})
        try:
            bundle = provider.get_features(HEALTH_PROBE_TICKER)
            results.append(
                {
                    "name": name,
                    "source_label": provider.source_label,
                    "available": bundle.available,
                    "fetched_at": bundle.fetched_at.isoformat(),
                    "key_scores": bundle.features if bundle.available else {},
                    "description": meta.get("description"),
                    "data_sources": meta.get("data_sources"),
                    "feature_descriptions": meta.get("feature_descriptions"),
                    "signal_logic": meta.get("signal_logic"),
                }
            )
        except Exception as exc:
            _LOG.warning("features: status probe failed for %s: %s", name, exc)
            results.append(build_unavailable_entry(name, label))
    return results
