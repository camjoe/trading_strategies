from __future__ import annotations

from pydantic import BaseModel, Field


class FeatureSignalsRequest(BaseModel):
    ticker: str = Field(min_length=1)
