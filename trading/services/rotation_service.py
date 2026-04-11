from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Callable, cast

from trading.domain.returns import safe_return_pct as safe_return_pct_impl
from trading.domain.rotation import resolve_rotation_overlay_mode
from trading.features.base import ExternalFeatureBundle
from trading.features.news_feature_provider import (
    NEWS_BUY_SENTIMENT_THRESHOLD,
    NEWS_HEADLINE_COUNT,
    NEWS_MIN_HEADLINES_REQUIRED,
    NEWS_SELL_SENTIMENT_THRESHOLD,
    NEWS_SENTIMENT_SCORE,
)
from trading.features.policy_feature_provider import (
    POLICY_MAX_DEFENSIVE_TILT,
    POLICY_RISK_OFF_SELL_THRESHOLD,
    POLICY_RISK_ON_BUY_THRESHOLD,
    POLICY_DEFENSIVE_TILT,
    POLICY_RISK_ON_SCORE,
)
from trading.features.social_feature_provider import (
    SOCIAL_MENTION_COUNT,
    SOCIAL_MIN_REDDIT_SENTIMENT,
    SOCIAL_REDDIT_SENTIMENT,
    SOCIAL_TREND_BUY_THRESHOLD,
    SOCIAL_TREND_EXIT_THRESHOLD,
    SOCIAL_TREND_SCORE,
)
from trading.utils.coercion import coerce_float

# Minimum completed live episodes required before the live component receives
# its full configured weight in hybrid rotation scoring.
MIN_LIVE_EPISODES_FOR_FULL_CONFIDENCE = 3

# Baseline hybrid score weighting: mostly backtest-driven until live evidence
# accumulates, with a smaller live overlay once strategy episodes are observed.
HYBRID_BACKTEST_WEIGHT = 0.70
HYBRID_LIVE_WEIGHT = 0.30

# Ticker used to query the policy provider for account-level regime context.
POLICY_REGIME_PROBE_TICKER = "SPY"

# Require multiple covered positions before ticker-level news/social signals can
# influence an account-level regime selection.
DEFAULT_ROTATION_OVERLAY_MIN_TICKERS = 2

# Require a clear majority of covered tickers to agree before the overlay nudges
# the base policy regime one step more defensive or aggressive.
DEFAULT_ROTATION_OVERLAY_CONFIDENCE_THRESHOLD = 0.50

# Overlay states nudge the policy-derived regime up or down by one notch rather
# than replacing it outright.
ROTATION_OVERLAY_DIRECTIONS = ("bearish", "bullish")
REGIME_STATE_ORDER = ("risk_off", "neutral", "risk_on")


def parse_as_of_iso(as_of_iso: str) -> datetime:
    text = as_of_iso.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def safe_return_pct(
    starting_equity: object,
    ending_equity: object,
    *,
    coerce_float_fn: Callable[[object], float | None],
) -> float | None:
    return safe_return_pct_impl(
        starting_equity,
        ending_equity,
        coerce_float_fn=coerce_float_fn,
    )


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _coerce_positive_int(value: object, *, default: int) -> int:
    parsed = coerce_float(value)
    if parsed is None or parsed <= 0:
        return default
    return int(parsed)


def _coerce_threshold(value: object, *, default: float) -> float:
    parsed = coerce_float(value)
    if parsed is None or parsed <= 0 or parsed > 1:
        return default
    return float(parsed)


def _account_value(account: sqlite3.Row, key: str) -> object | None:
    if hasattr(account, "keys") and key in account.keys():
        return account[key]
    if isinstance(account, dict):
        return account.get(key)
    try:
        return account[key]
    except (KeyError, TypeError, IndexError):
        return None


def classify_policy_regime(
    *,
    risk_on_score: object,
    defensive_tilt: object,
    coerce_float_fn: Callable[[object], float | None],
) -> str | None:
    score = coerce_float_fn(risk_on_score)
    tilt = coerce_float_fn(defensive_tilt)
    if score is None or tilt is None:
        return None
    if score >= POLICY_RISK_ON_BUY_THRESHOLD and tilt <= POLICY_MAX_DEFENSIVE_TILT:
        return "risk_on"
    if score < POLICY_RISK_OFF_SELL_THRESHOLD or tilt > POLICY_MAX_DEFENSIVE_TILT:
        return "risk_off"
    return "neutral"


def fetch_rotation_overlay_tickers(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
    *,
    load_trades_fn: Callable[[sqlite3.Connection, int], list[sqlite3.Row]],
    compute_account_state_fn: Callable[[float, list[sqlite3.Row]], object],
) -> list[str]:
    state = cast(
        object,
        compute_account_state_fn(float(account["initial_cash"]), load_trades_fn(conn, int(account["id"]))),
    )
    positions = cast(dict[str, float], getattr(state, "positions", {}))
    return sorted(ticker for ticker, qty in positions.items() if float(qty) > 0)


def _classify_news_overlay_vote(
    bundle: ExternalFeatureBundle,
    *,
    coerce_float_fn: Callable[[object], float | None],
) -> int | None:
    if not bundle.available:
        return None
    score = coerce_float_fn(bundle.get(NEWS_SENTIMENT_SCORE))
    headline_count = coerce_float_fn(bundle.get(NEWS_HEADLINE_COUNT))
    if score is None or headline_count is None or headline_count < NEWS_MIN_HEADLINES_REQUIRED:
        return None
    if score >= NEWS_BUY_SENTIMENT_THRESHOLD:
        return 1
    if score <= NEWS_SELL_SENTIMENT_THRESHOLD:
        return -1
    return 0


def _classify_social_overlay_vote(
    bundle: ExternalFeatureBundle,
    *,
    coerce_float_fn: Callable[[object], float | None],
) -> int | None:
    if not bundle.available:
        return None
    trend_score = coerce_float_fn(bundle.get(SOCIAL_TREND_SCORE))
    mention_count = coerce_float_fn(bundle.get(SOCIAL_MENTION_COUNT))
    reddit_sentiment = coerce_float_fn(bundle.get(SOCIAL_REDDIT_SENTIMENT))
    if trend_score is None or mention_count is None or reddit_sentiment is None:
        return None
    if trend_score >= SOCIAL_TREND_BUY_THRESHOLD and mention_count > 0 and reddit_sentiment > 0:
        return 1
    if trend_score <= SOCIAL_TREND_EXIT_THRESHOLD and reddit_sentiment <= SOCIAL_MIN_REDDIT_SENTIMENT:
        return -1
    return 0


def select_rotation_overlay_direction(
    account: sqlite3.Row,
    tickers: list[str],
    *,
    overlay_mode: str,
    fetch_news_features_fn: Callable[[str], ExternalFeatureBundle] | None,
    fetch_social_features_fn: Callable[[str], ExternalFeatureBundle] | None,
    coerce_float_fn: Callable[[object], float | None] = coerce_float,
) -> str | None:
    if overlay_mode == "none" or not tickers:
        return None

    covered_tickers = 0
    net_votes = 0
    for ticker in tickers:
        source_votes: list[int] = []
        if overlay_mode in {"news", "news_social"} and fetch_news_features_fn is not None:
            news_vote = _classify_news_overlay_vote(
                fetch_news_features_fn(ticker),
                coerce_float_fn=coerce_float_fn,
            )
            if news_vote is not None:
                source_votes.append(news_vote)
        if overlay_mode in {"social", "news_social"} and fetch_social_features_fn is not None:
            social_vote = _classify_social_overlay_vote(
                fetch_social_features_fn(ticker),
                coerce_float_fn=coerce_float_fn,
            )
            if social_vote is not None:
                source_votes.append(social_vote)
        if not source_votes:
            continue
        covered_tickers += 1
        combined_vote = sum(source_votes) / len(source_votes)
        if combined_vote > 0:
            net_votes += 1
        elif combined_vote < 0:
            net_votes -= 1

    min_tickers = _coerce_positive_int(
        _account_value(account, "rotation_overlay_min_tickers"),
        default=DEFAULT_ROTATION_OVERLAY_MIN_TICKERS,
    )
    if covered_tickers < min_tickers or net_votes == 0:
        return None

    confidence_threshold = _coerce_threshold(
        _account_value(account, "rotation_overlay_confidence_threshold"),
        default=DEFAULT_ROTATION_OVERLAY_CONFIDENCE_THRESHOLD,
    )
    confidence = abs(net_votes) / covered_tickers
    if confidence < confidence_threshold:
        return None

    return "bullish" if net_votes > 0 else "bearish"


def apply_rotation_overlay_to_regime(regime_state: str, overlay_direction: str | None) -> str:
    if regime_state not in REGIME_STATE_ORDER or overlay_direction not in ROTATION_OVERLAY_DIRECTIONS:
        return regime_state
    current_index = REGIME_STATE_ORDER.index(regime_state)
    step = 1 if overlay_direction == "bullish" else -1
    next_index = max(0, min(len(REGIME_STATE_ORDER) - 1, current_index + step))
    return REGIME_STATE_ORDER[next_index]


def select_regime_strategy(
    account: sqlite3.Row,
    *,
    parse_rotation_schedule_fn: Callable[[object | None], list[str]],
    resolve_active_strategy_fn: Callable[[sqlite3.Row], str],
    resolve_rotation_regime_strategy_fn: Callable[[sqlite3.Row, str], str | None],
    fetch_policy_features_fn: Callable[[str], ExternalFeatureBundle],
    conn: sqlite3.Connection | None = None,
    fetch_news_features_fn: Callable[[str], ExternalFeatureBundle] | None = None,
    fetch_social_features_fn: Callable[[str], ExternalFeatureBundle] | None = None,
    fetch_rotation_overlay_tickers_fn: Callable[[sqlite3.Connection, sqlite3.Row], list[str]] | None = None,
    resolve_rotation_overlay_mode_fn: Callable[[sqlite3.Row], str] = resolve_rotation_overlay_mode,
    coerce_float_fn: Callable[[object], float | None] = coerce_float,
) -> str | None:
    schedule = parse_rotation_schedule_fn(account["rotation_schedule"])
    if not schedule:
        return None

    active_strategy = resolve_active_strategy_fn(account)
    bundle = fetch_policy_features_fn(POLICY_REGIME_PROBE_TICKER)
    if not bundle.available:
        return active_strategy

    regime_state = classify_policy_regime(
        risk_on_score=bundle.get(POLICY_RISK_ON_SCORE),
        defensive_tilt=bundle.get(POLICY_DEFENSIVE_TILT),
        coerce_float_fn=coerce_float_fn,
    )
    if regime_state is None:
        return active_strategy

    overlay_mode = resolve_rotation_overlay_mode_fn(account)
    if (
        overlay_mode != "none"
        and conn is not None
        and fetch_rotation_overlay_tickers_fn is not None
    ):
        overlay_direction = select_rotation_overlay_direction(
            account,
            fetch_rotation_overlay_tickers_fn(conn, account),
            overlay_mode=overlay_mode,
            fetch_news_features_fn=fetch_news_features_fn,
            fetch_social_features_fn=fetch_social_features_fn,
            coerce_float_fn=coerce_float_fn,
        )
        regime_state = apply_rotation_overlay_to_regime(regime_state, overlay_direction)

    selected = resolve_rotation_regime_strategy_fn(account, regime_state)
    if not selected:
        return active_strategy

    return selected if selected in schedule else active_strategy


def compute_live_account_metrics(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
    *,
    load_trades_fn: Callable[[sqlite3.Connection, int], list[sqlite3.Row]],
    compute_account_state_fn: Callable[[float, list[sqlite3.Row]], object],
    fetch_latest_prices_fn: Callable[[list[str]], dict[str, float]],
    compute_market_value_and_unrealized_fn: Callable[[dict[str, float], dict[str, float], dict[str, float]], tuple[float, float]],
) -> dict[str, float]:
    state = cast(
        object,
        compute_account_state_fn(float(account["initial_cash"]), load_trades_fn(conn, int(account["id"]))),
    )
    positions = cast(dict[str, float], getattr(state, "positions"))
    avg_cost = cast(dict[str, float], getattr(state, "avg_cost"))
    prices = fetch_latest_prices_fn(sorted(positions.keys())) if positions else {}
    market_value, _unrealized = compute_market_value_and_unrealized_fn(positions, avg_cost, prices)
    equity = float(getattr(state, "cash", 0.0)) + float(market_value)
    return {
        "equity": equity,
        "realized_pnl": float(getattr(state, "realized_pnl", 0.0)),
    }


def sync_rotation_episode(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
    as_of_iso: str,
    *,
    resolve_active_strategy_fn: Callable[[sqlite3.Row], str],
    fetch_open_rotation_episode_fn: Callable[..., sqlite3.Row | None],
    insert_rotation_episode_fn: Callable[..., None],
    close_rotation_episode_fn: Callable[..., None],
    fetch_snapshot_count_between_fn: Callable[..., int],
    compute_live_account_metrics_fn: Callable[[sqlite3.Connection, sqlite3.Row], dict[str, float]],
) -> None:
    if not bool(int(cast(int | float | str | bytes | bytearray, account["rotation_enabled"] or 0))):
        return

    active_strategy = resolve_active_strategy_fn(account)
    if not active_strategy:
        return

    metrics = compute_live_account_metrics_fn(conn, account)
    open_episode = fetch_open_rotation_episode_fn(conn, account_id=int(account["id"]))
    episode_started_at = str(account["rotation_last_at"] or as_of_iso)

    if open_episode is None:
        insert_rotation_episode_fn(
            conn,
            account_id=int(account["id"]),
            strategy_name=active_strategy,
            started_at=episode_started_at,
            starting_equity=float(metrics["equity"]),
            starting_realized_pnl=float(metrics["realized_pnl"]),
        )
        return

    if str(open_episode["strategy_name"]) == active_strategy:
        return

    snapshot_count = fetch_snapshot_count_between_fn(
        conn,
        account_id=int(account["id"]),
        start_iso=str(open_episode["started_at"]),
        end_iso=as_of_iso,
    )
    starting_realized_pnl = float(open_episode["starting_realized_pnl"])
    close_rotation_episode_fn(
        conn,
        episode_id=int(open_episode["id"]),
        ended_at=as_of_iso,
        ending_equity=float(metrics["equity"]),
        ending_realized_pnl=float(metrics["realized_pnl"]),
        realized_pnl_delta=float(metrics["realized_pnl"]) - starting_realized_pnl,
        snapshot_count=snapshot_count,
    )
    insert_rotation_episode_fn(
        conn,
        account_id=int(account["id"]),
        strategy_name=active_strategy,
        started_at=as_of_iso,
        starting_equity=float(metrics["equity"]),
        starting_realized_pnl=float(metrics["realized_pnl"]),
    )


def select_optimal_strategy(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
    as_of_iso: str,
    *,
    parse_rotation_schedule_fn: Callable[[object | None], list[str]],
    parse_as_of_iso_fn: Callable[[str], datetime],
    fetch_strategy_backtest_returns_fn: Callable[..., list[tuple[str, float]]],
    resolve_optimality_mode_fn: Callable[[sqlite3.Row], str],
    fetch_closed_rotation_episodes_fn: Callable[..., list[sqlite3.Row]] | None = None,
) -> str | None:
    schedule = parse_rotation_schedule_fn(account["rotation_schedule"])
    if not schedule:
        return None

    lookback_days = int(account["rotation_lookback_days"] or 180)
    as_of_dt = parse_as_of_iso_fn(as_of_iso)
    end_day = as_of_dt.date().isoformat()
    start_day = (as_of_dt - timedelta(days=lookback_days)).date().isoformat()

    returns = fetch_strategy_backtest_returns_fn(
        conn,
        account_id=int(account["id"]),
        strategy_names=schedule,
        start_day=start_day,
        end_day=end_day,
    )

    if not returns:
        return None

    by_strategy: dict[str, list[float]] = {}
    latest_by_strategy: dict[str, float] = {}
    for strategy_name, ret in returns:
        by_strategy.setdefault(strategy_name, []).append(ret)
        if strategy_name not in latest_by_strategy:
            latest_by_strategy[strategy_name] = ret

    if not by_strategy:
        by_strategy = {}

    optimality_mode = resolve_optimality_mode_fn(account)
    scores: dict[str, float] = {}
    if optimality_mode == "hybrid_weighted":
        live_scores: dict[str, list[float]] = {}
        if fetch_closed_rotation_episodes_fn is not None:
            closed_rows = fetch_closed_rotation_episodes_fn(
                conn,
                account_id=int(account["id"]),
                strategy_names=schedule,
                start_iso=f"{start_day}T00:00:00Z",
                end_iso=as_of_iso,
            )
            for row in closed_rows:
                starting_equity = row["starting_equity"]
                ending_equity = row["ending_equity"]
                if starting_equity is None or ending_equity is None:
                    continue
                live_return = safe_return_pct(starting_equity, ending_equity, coerce_float_fn=coerce_float)
                if live_return is None:
                    continue
                live_scores.setdefault(str(row["strategy_name"]), []).append(float(live_return))

        for strategy_name in schedule:
            backtest_score = _average(by_strategy.get(strategy_name, []))
            live_values = live_scores.get(strategy_name, [])
            live_score = _average(live_values)
            if backtest_score is None and live_score is None:
                continue
            if backtest_score is None:
                assert live_score is not None
                scores[strategy_name] = float(live_score)
                continue
            if live_score is None:
                scores[strategy_name] = float(backtest_score)
                continue
            live_confidence = min(len(live_values) / MIN_LIVE_EPISODES_FOR_FULL_CONFIDENCE, 1.0)
            live_weight = HYBRID_LIVE_WEIGHT * live_confidence
            backtest_weight = HYBRID_BACKTEST_WEIGHT + (HYBRID_LIVE_WEIGHT - live_weight)
            scores[strategy_name] = (float(backtest_score) * backtest_weight) + (float(live_score) * live_weight)
    elif optimality_mode == "average_return":
        for strategy_name, values in by_strategy.items():
            scores[strategy_name] = sum(values) / len(values)
    else:
        scores = dict(latest_by_strategy)

    if not scores:
        return None

    best_strategy = max(scores.items(), key=lambda item: item[1])[0]
    return best_strategy if best_strategy in schedule else None


def rotate_account_if_due(
    conn: sqlite3.Connection,
    account_name: str,
    account: sqlite3.Row,
    now_iso: str,
    *,
    is_rotation_due_fn: Callable[[sqlite3.Row], bool],
    resolve_rotation_mode_fn: Callable[[sqlite3.Row], str],
    select_optimal_strategy_fn: Callable[[sqlite3.Connection, sqlite3.Row, str], str | None],
    resolve_active_strategy_fn: Callable[[sqlite3.Row], str],
    parse_rotation_schedule_fn: Callable[[object | None], list[str]],
    next_rotation_state_fn: Callable[[sqlite3.Row, str], dict[str, object]],
    update_account_rotation_state_fn: Callable[..., None],
    get_account_fn: Callable[[sqlite3.Connection, str], sqlite3.Row],
) -> sqlite3.Row:
    if not is_rotation_due_fn(account):
        return account

    rotation_mode = resolve_rotation_mode_fn(account)
    if rotation_mode in {"optimal", "regime"}:
        selected = select_optimal_strategy_fn(conn, account, now_iso)
        active = selected or resolve_active_strategy_fn(account)
        schedule = parse_rotation_schedule_fn(account["rotation_schedule"])
        if schedule and active in schedule:
            active_idx = schedule.index(active)
        else:
            active_idx = int(cast(int | float | str | bytes | bytearray, account["rotation_active_index"] or 0))
        next_state = {
            "rotation_active_index": active_idx,
            "rotation_active_strategy": active,
            "rotation_last_at": now_iso,
        }
    else:
        next_state = next_rotation_state_fn(account, now_iso)

    update_account_rotation_state_fn(
        conn,
        account_id=int(account["id"]),
        strategy=str(next_state["rotation_active_strategy"]),
        rotation_active_index=int(
            cast(int | float | str | bytes | bytearray, next_state["rotation_active_index"])
        ),
        rotation_active_strategy=str(next_state["rotation_active_strategy"]),
        rotation_last_at=str(next_state["rotation_last_at"]),
    )
    return get_account_fn(conn, account_name)
