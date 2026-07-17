"""Loader for the operator-editable symbol→sector reference data.

The data lives in ``src/infrastructure/config/symbol_sectors.json`` as a flat
JSON object of ``{"SYMBOL": "sector"}``.  It is injected into
``RiskGateConfig.symbol_sector_map`` at the service layer so the domain
gate and models stay free of file I/O.

A missing file yields an empty map (sector-concentration limits simply do not
apply), matching how ``load_trade_caps_config`` degrades when its config is
absent.

The initial config seed covers the legacy/default trade universe plus broad ETF
symbols, not every symbol in the named universe files.  Unmapped symbols are
treated as uncategorized for sector-concentration checks until the reference
data is expanded.
"""

from __future__ import annotations

import json
from pathlib import Path

from common.paths.project_paths import SYMBOL_SECTORS_PATH


def load_symbol_sector_map(config_path: Path = SYMBOL_SECTORS_PATH) -> dict[str, str]:
    if not config_path.exists():
        return {}

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("symbol_sectors config must be a JSON object of symbol -> sector")

    sector_map: dict[str, str] = {}
    for symbol, sector in raw.items():
        if not isinstance(symbol, str) or not isinstance(sector, str):
            raise ValueError("symbol_sectors entries must map a string symbol to a string sector")
        normalized_symbol = symbol.upper().strip()
        normalized_sector = sector.strip().lower()
        if normalized_symbol and normalized_sector:
            sector_map[normalized_symbol] = normalized_sector
    return sector_map
