from __future__ import annotations

import argparse
import random

from common.git import get_repo_root
from infrastructure.brokers.factory import get_broker_for_account
from infrastructure.database.connection import db_session
from infrastructure.feature_providers.news_provider import NewsFeatureProvider
from infrastructure.feature_providers.policy_provider import PolicyFeatureProvider
from infrastructure.feature_providers.social_provider import SocialFeatureProvider
from infrastructure.market_data.factory import build_provider
from trading.domain.feature_provider import FeatureFetcherSet
from trading.services.auto_trading import (
    is_runtime_submission_window_open,
    resolve_account_names,
    resolve_market_inputs,
    run_accounts,
    run_for_account,
)
from trading.services.execution.constants import KILL_SWITCH_REASON_BROKER_API_ANOMALY
from trading.services.profiles.source import DEFAULT_TICKERS_FILE

REPO_ROOT = get_repo_root(__file__)
__all__ = ["parse_args", "main", "run_for_account"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute signal-driven daily paper trades per account (up to --max-trades)."
    )
    parser.add_argument(
        "--accounts",
        required=True,
        help="Comma-separated account names, e.g. momentum_5k,meanrev_5k",
    )
    parser.add_argument(
        "--tickers-file",
        default=DEFAULT_TICKERS_FILE,
        help=f"Path to ticker universe file (default: {DEFAULT_TICKERS_FILE})",
    )
    parser.add_argument("--max-trades", type=int, default=5, help="Maximum trades per account")
    parser.add_argument("--fee", type=float, default=0.0, help="Per-trade fee")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed")
    return parser.parse_args()


def main() -> int:
    """Run the accounts and return the process exit code.

    Exits non-zero when the broker misbehaved mid-submission. That is the one
    outcome where real orders may exist in an unknown state, so it should fail
    the daily run's step rather than read as a clean pass. Every other halt —
    a stale-price or reconciliation kill switch, or the trade throttle — is a
    control working as designed: the run stays green and the workflow reports it
    via ``kill_switch_accounts``.
    """
    args = parse_args()
    if args.max_trades < 1:
        raise ValueError("--max-trades must be >= 1")

    if args.seed is not None:
        random.seed(args.seed)

    accounts = resolve_account_names(args.accounts)
    # The runtime declines to submit outside US regular equity hours. Say so up
    # front — otherwise a closed market and a genuine no-signal day both read as
    # "executed 0 trades".
    if not is_runtime_submission_window_open():
        print("Market closed: no orders will be submitted (US regular equity hours only).")

    # Composition root: build the market-data provider once and inject it through
    # the market-input + rotation paths (no global locator access inside services).
    provider = build_provider()
    universe, prices, iv_rank_proxy, histories = resolve_market_inputs(args.tickers_file, provider=provider)
    policy_provider = PolicyFeatureProvider()
    news_provider = NewsFeatureProvider()
    social_provider = SocialFeatureProvider()
    feature_fetchers = FeatureFetcherSet(
        fetch_policy=policy_provider.get_features,
        fetch_news=news_provider.get_features,
        fetch_social=social_provider.get_features,
    )

    with db_session() as conn:
        results = run_accounts(
            conn,
            account_names=accounts,
            universe=universe,
            prices=prices,
            iv_rank_proxy=iv_rank_proxy,
            max_trades=args.max_trades,
            fee=args.fee,
            histories=histories,
            broker_factory=get_broker_for_account,
            feature_fetchers=feature_fetchers,
            provider=provider,
        )

    for result in results:
        halted = f" (halted: {', '.join(result.kill_switch_reasons)})" if result.halted else ""
        print(f"{result.account_name}: executed {result.submitted_count} trades{halted}")

    broker_anomalies = [
        r.account_name for r in results if KILL_SWITCH_REASON_BROKER_API_ANOMALY in r.kill_switch_reasons
    ]
    if broker_anomalies:
        print(f"Broker API anomaly during submission for: {', '.join(broker_anomalies)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
