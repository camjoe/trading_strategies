"""Integration test for the policy feature provider feeding rotation.

Covers the core capability "feature providers" from ``docs/overview.md``: the
policy (ETF-proxy) provider is the one provider that reaches a decision today,
as the regime input to rotation's regime-fit component. The test drives the
real provider over the deterministic demo market data, then feeds its bundle
into the real rotation metric builder and checks the regime score is consumed.
"""

from __future__ import annotations

import math
import sqlite3

from infrastructure.feature_providers.policy_provider import PolicyFeatureProvider
from infrastructure.market_data.demo_provider import DemoMarketDataProvider
from trading.domain.feature_provider import POLICY_DEFENSIVE_TILT, POLICY_RISK_ON_SCORE
from trading.services.accounts.mutations import create_account, get_account
from trading.services.books.rotation.metrics import build_rotation_strategy_metrics
from trading.services.strategy_catalog.seeding import seed_strategy_catalog

STRATEGY = "trend"


def test_policy_provider_bundle_feeds_the_rotation_regime_fit(conn: sqlite3.Connection) -> None:
    provider = PolicyFeatureProvider(market_data_provider=DemoMarketDataProvider())

    bundle = provider.get_features("AAPL")
    assert bundle.available is True
    risk_on = bundle.get(POLICY_RISK_ON_SCORE)
    assert risk_on is not None
    assert 0.0 <= risk_on <= 1.0
    assert bundle.get(POLICY_DEFENSIVE_TILT) is not None

    seed_strategy_catalog(conn)
    create_account(conn, "acct_regime", STRATEGY, 1_000.0, "SPY")
    account = get_account(conn, "acct_regime")

    metrics = build_rotation_strategy_metrics(
        conn,
        account=account,
        strategy_name=STRATEGY,
        fetch_regime=provider.get_features,
    )

    # The regime score reached the metric: a real, finite component value.
    assert math.isfinite(metrics.regime_fit)
    assert metrics.strategy_name == STRATEGY
