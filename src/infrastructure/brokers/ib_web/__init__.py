"""Interactive Brokers Web API client package.

Settings/config loading (`settings`), process-local pacing (`pacing`), and the HTTP
client (`client`) are separate modules; the public surface is re-exported here.
"""

from __future__ import annotations

from infrastructure.brokers.ib_web.client import IbWebApiContract, InteractiveBrokersWebClient
from infrastructure.brokers.ib_web.pacing import IbWebApiPacingLimiter
from infrastructure.brokers.ib_web.settings import IbWebApiSettings, load_ib_web_api_settings

__all__ = [
    "IbWebApiContract",
    "IbWebApiPacingLimiter",
    "IbWebApiSettings",
    "InteractiveBrokersWebClient",
    "load_ib_web_api_settings",
]
