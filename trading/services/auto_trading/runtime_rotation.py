"""Rotation and feature-provider helpers for runtime auto-trading orchestration."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable

from trading.models import AccountRecord
from trading.features.base import ExternalFeatureBundle
from trading.features.news_feature_provider import NewsFeatureProvider
from trading.features.policy_feature_provider import PolicyFeatureProvider
from trading.features.social_feature_provider import SocialFeatureProvider
from trading.services.auto_trading.rotation import (
    compute_live_account_metrics as compute_live_account_metrics_impl,
    fetch_rotation_overlay_tickers as fetch_rotation_overlay_tickers_impl,
    sync_rotation_episode as sync_rotation_episode_impl,
)
from trading.services.auto_trading.rotation_bridge import (
    RotationDeps,
    rotate_runtime_account_if_due as rotate_runtime_account_if_due_impl,
    select_account_rotation_strategy as select_account_rotation_strategy_impl,
)

logger = logging.getLogger(__name__)

_policy_rotation_provider: PolicyFeatureProvider | None = None
_news_rotation_provider: NewsFeatureProvider | None = None
_social_rotation_provider: SocialFeatureProvider | None = None


def fetch_policy_rotation_bundle(ticker: str) -> ExternalFeatureBundle:
    global _policy_rotation_provider
    if _policy_rotation_provider is None:
        _policy_rotation_provider = PolicyFeatureProvider()
    try:
        return _policy_rotation_provider.get_features(ticker)
    except Exception as exc:
        logger.warning("Policy rotation provider failed for %s: %s", ticker, exc, exc_info=True)
        return ExternalFeatureBundle.unavailable(source="etf-proxies")


def fetch_news_rotation_bundle(ticker: str) -> ExternalFeatureBundle:
    global _news_rotation_provider
    if _news_rotation_provider is None:
        _news_rotation_provider = NewsFeatureProvider()
    try:
        return _news_rotation_provider.get_features(ticker)
    except Exception as exc:
        logger.warning("News rotation provider failed for %s: %s", ticker, exc, exc_info=True)
        return ExternalFeatureBundle.unavailable(source="rss+vader")


def fetch_social_rotation_bundle(ticker: str) -> ExternalFeatureBundle:
    global _social_rotation_provider
    if _social_rotation_provider is None:
        _social_rotation_provider = SocialFeatureProvider()
    try:
        return _social_rotation_provider.get_features(ticker)
    except Exception as exc:
        logger.warning("Social rotation provider failed for %s: %s", ticker, exc, exc_info=True)
        return ExternalFeatureBundle.unavailable(source="reddit+gtrends")


def fetch_runtime_rotation_overlay_tickers(
    conn: sqlite3.Connection,
    account: AccountRecord,
) -> list[str]:
    return fetch_rotation_overlay_tickers_impl(conn, account)


def compute_runtime_live_account_metrics(
    conn: sqlite3.Connection,
    account: AccountRecord,
) -> dict[str, float]:
    return compute_live_account_metrics_impl(conn, account)


def select_runtime_rotation_strategy(
    conn: sqlite3.Connection,
    account: AccountRecord,
    as_of_iso: str,
    *,
    fetch_strategy_backtest_returns_fn: Callable[..., object],
    fetch_closed_rotation_episodes_fn: Callable[..., object],
) -> str | None:
    return select_account_rotation_strategy_impl(
        conn,
        account,
        as_of_iso,
        fetch_strategy_backtest_returns_fn=fetch_strategy_backtest_returns_fn,
        fetch_policy_features_fn=fetch_policy_rotation_bundle,
        fetch_news_features_fn=fetch_news_rotation_bundle,
        fetch_social_features_fn=fetch_social_rotation_bundle,
        fetch_rotation_overlay_tickers_fn=fetch_runtime_rotation_overlay_tickers,
        fetch_closed_rotation_episodes_fn=fetch_closed_rotation_episodes_fn,
    )


def sync_runtime_rotation_episode(
    conn: sqlite3.Connection,
    account: AccountRecord,
    now_iso: str,
    *,
    fetch_open_rotation_episode_fn: Callable[..., object],
    insert_rotation_episode_fn: Callable[..., object],
    close_rotation_episode_fn: Callable[..., object],
    fetch_snapshot_count_between_fn: Callable[..., object],
) -> None:
    if not hasattr(conn, "execute"):
        return
    sync_rotation_episode_impl(
        conn,
        account,
        now_iso,
        fetch_open_rotation_episode_fn=fetch_open_rotation_episode_fn,
        insert_rotation_episode_fn=insert_rotation_episode_fn,
        close_rotation_episode_fn=close_rotation_episode_fn,
        fetch_snapshot_count_between_fn=fetch_snapshot_count_between_fn,
        compute_live_account_metrics_fn=compute_runtime_live_account_metrics,
    )


def rotate_runtime_account(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    now_iso: str,
    *,
    is_rotation_due_fn: Callable[..., bool],
    update_account_rotation_state_fn: Callable[..., object],
    get_account_fn: Callable[..., AccountRecord],
    fetch_strategy_backtest_returns_fn: Callable[..., object],
    fetch_closed_rotation_episodes_fn: Callable[..., object],
    fetch_open_rotation_episode_fn: Callable[..., object],
    insert_rotation_episode_fn: Callable[..., object],
    close_rotation_episode_fn: Callable[..., object],
    fetch_snapshot_count_between_fn: Callable[..., object],
) -> AccountRecord:
    sync_runtime_rotation_episode(
        conn,
        account,
        now_iso,
        fetch_open_rotation_episode_fn=fetch_open_rotation_episode_fn,
        insert_rotation_episode_fn=insert_rotation_episode_fn,
        close_rotation_episode_fn=close_rotation_episode_fn,
        fetch_snapshot_count_between_fn=fetch_snapshot_count_between_fn,
    )
    deps = RotationDeps(
        is_rotation_due_fn=lambda row: is_rotation_due_fn(row, as_of_iso=now_iso),
        select_optimal_strategy_fn=lambda c, a, iso: select_runtime_rotation_strategy(
            c,
            a,
            iso,
            fetch_strategy_backtest_returns_fn=fetch_strategy_backtest_returns_fn,
            fetch_closed_rotation_episodes_fn=fetch_closed_rotation_episodes_fn,
        ),
        update_account_rotation_state_fn=update_account_rotation_state_fn,
        get_account_fn=get_account_fn,
    )
    rotated = rotate_runtime_account_if_due_impl(conn, account_name, account, now_iso, deps)
    sync_runtime_rotation_episode(
        conn,
        rotated,
        now_iso,
        fetch_open_rotation_episode_fn=fetch_open_rotation_episode_fn,
        insert_rotation_episode_fn=insert_rotation_episode_fn,
        close_rotation_episode_fn=close_rotation_episode_fn,
        fetch_snapshot_count_between_fn=fetch_snapshot_count_between_fn,
    )
    return rotated
