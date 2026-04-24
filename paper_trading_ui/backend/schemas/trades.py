from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ManualTradeRequest(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    qty: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = Field(default=0.0, ge=0)
