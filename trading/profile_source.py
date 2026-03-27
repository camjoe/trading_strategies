"""Account profile source abstractions.

Current implementation supports JSON file-backed profiles and keeps a stable
interface for future profile storage backends (for example, database-backed
sources).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class AccountProfileSource(Protocol):
    def load_profiles(self) -> list[dict[str, object]]:
        ...


class JsonAccountProfileSource:
    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)

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
