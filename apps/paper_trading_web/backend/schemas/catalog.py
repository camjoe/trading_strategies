from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CatalogRunRequest(BaseModel):
    name: str = Field(min_length=1)
    values: dict[str, Any] = Field(default_factory=dict)
