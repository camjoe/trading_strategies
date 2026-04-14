"""Account profile source abstractions.

Current implementation supports JSON file-backed profiles and keeps a stable
interface for future profile storage backends (for example, database-backed
sources).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


DEFAULT_ACCOUNT_PROFILES_FILE = "trading/config/account_profiles/default.json"
DEFAULT_TICKERS_FILE = "trading/config/trade_universe.txt"


def _profiles_dir_candidates() -> list[Path]:
    trading_root = Path(__file__).resolve().parents[1]
    return [
        trading_root / "config" / "account_profiles",
        trading_root / "account_profiles",
    ]


def get_builtin_profile_preset_path(preset: str) -> Path:
    preset_name = preset.strip().lower()
    for profiles_dir in _profiles_dir_candidates():
        candidate = profiles_dir / f"{preset_name}.json"
        if candidate.exists():
            return candidate
    # Return preferred target location for clear error paths when missing.
    return _profiles_dir_candidates()[0] / f"{preset_name}.json"


def resolve_profile_file_path(file_path: str | Path) -> Path:
    candidate = Path(file_path)
    if candidate.exists():
        return candidate

    legacy_prefix = "trading/account_profiles/"
    normalized = candidate.as_posix()
    if normalized.startswith(legacy_prefix):
        suffix = normalized[len(legacy_prefix) :]
        return Path("trading/config/account_profiles") / suffix

    return candidate


class AccountProfileSource(Protocol):
    def load_profiles(self) -> list[dict[str, object]]:
        ...


class JsonAccountProfileSource:
    def __init__(self, file_path: str | Path) -> None:
        self.file_path = resolve_profile_file_path(file_path)

    def load_profiles(self) -> list[dict[str, object]]:
        if not self.file_path.exists():
            raise FileNotFoundError(f"Profile file not found: {self.file_path}")

        raw = json.loads(self.file_path.read_text(encoding="utf-8"))

        if isinstance(raw, dict):
            profiles = raw.get("accounts", [])
        else:
            profiles = raw

        if not isinstance(profiles, list):
            raise ValueError("Profile file must be a list or an object with an 'accounts' list.")

        out: list[dict[str, object]] = []
        for i, item in enumerate(profiles, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Account profile at index {i} is not an object.")
            if "name" not in item or not str(item["name"]).strip():
                raise ValueError(f"Account profile at index {i} is missing required 'name'.")
            out.append(item)

        return out
