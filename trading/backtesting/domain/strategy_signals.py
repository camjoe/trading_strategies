from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import pandas as pd

from trading.backtesting.domain.indicators_adapter import calculate_macd, calculate_rs_rsi

from common.constants import (
    MACD_MIN_HISTORY,
    RSI_DEFAULT_WINDOW,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    TRADING_DAYS_PER_YEAR,
)
from trading.backtesting.trading_bridge import (
    POLICY_DEFENSIVE_TILT,
    POLICY_MAX_DEFENSIVE_TILT,
    POLICY_RISK_OFF_SELL_THRESHOLD,
    POLICY_RISK_ON_BUY_THRESHOLD,
    POLICY_RISK_ON_SCORE,
)
from trading.backtesting.trading_bridge import (
    NEWS_BUY_SENTIMENT_THRESHOLD,
    NEWS_HEADLINE_COUNT,
    NEWS_MIN_HEADLINES_REQUIRED,
    NEWS_SELL_SENTIMENT_THRESHOLD,
    NEWS_SENTIMENT_SCORE,
)
from trading.backtesting.trading_bridge import (
    SOCIAL_MENTION_COUNT,
    SOCIAL_MIN_REDDIT_SENTIMENT,
    SOCIAL_REDDIT_SENTIMENT,
    SOCIAL_TREND_BUY_THRESHOLD,
    SOCIAL_TREND_EXIT_THRESHOLD,
    SOCIAL_TREND_SCORE,
)

StrategyParams = Mapping[str, Any]
SignalFunction = Callable[[pd.Series, StrategyParams, pd.DataFrame | None], str]

# Minimum fraction of available proxy data required to trust a topic-proxy feature signal
PROXY_AVAILABILITY_THRESHOLD = 0.5


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    signal_fn: SignalFunction
    default_params: dict[str, Any]
    aliases: tuple[str, ...] = ()
    description: str = ""
    required_features: tuple[str, ...] = ()
    # Broad behavioral family: "trend", "mean_reversion", "neutral", or "alternative".
    # Used by policy layers to set sell bias and other style-dependent behavior
    # without resorting to fragile string matching on strategy names.
    # "alternative" = external-data-driven strategies (news, social, policy);
    # see trading/features/ for the provider infrastructure.
    strategy_style: str = "neutral"


def _feature_value(feature_history: pd.DataFrame | None, column: str) -> float | None:
    if feature_history is None or feature_history.empty or column not in feature_history.columns:
        return None
    series = pd.to_numeric(feature_history[column], errors="coerce").dropna()
    if series.empty:
        return None
    val = float(series.iloc[-1])
    # Treat non-finite feature values (inf/-inf) as unavailable so signal
    # logic never makes decisions based on unbounded inputs.
    return val if math.isfinite(val) else None


def _trend_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    fast_window = int(params.get("fast_window", 10))
    slow_window = int(params.get("slow_window", 20))
    min_history = max(30, slow_window)
    if len(history) < min_history:
        return "hold"

    close = float(history.iloc[-1])
    if not math.isfinite(close):
        return "hold"
    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    if not math.isfinite(sma_fast) or not math.isfinite(sma_slow):
        return "hold"
    if close > sma_fast > sma_slow:
        return "buy"
    if close < sma_fast:
        return "sell"
    return "hold"


def _mean_reversion_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    window = int(params.get("window", 20))
    band_pct = float(params.get("band_pct", 0.02))
    if len(history) < 30:
        return "hold"

    close = float(history.iloc[-1])
    if not math.isfinite(close):
        return "hold"
    sma_mid = float(history.tail(window).mean())
    if not math.isfinite(sma_mid):
        return "hold"
    if close < (sma_mid * (1.0 - band_pct)):
        return "buy"
    if close > (sma_mid * (1.0 + band_pct)):
        return "sell"
    return "hold"


def _rsi_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    window = int(params.get("window", RSI_DEFAULT_WINDOW))
    oversold = float(params.get("oversold", RSI_OVERSOLD))
    overbought = float(params.get("overbought", RSI_OVERBOUGHT))
    min_history = max(30, window + 1)
    if len(history) < min_history:
        return "hold"

    _rs, rsi = calculate_rs_rsi(history, window=window)
    last_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else float("nan")
    if pd.isna(last_rsi) or not math.isfinite(last_rsi):
        return "hold"
    if last_rsi < oversold:
        return "buy"
    if last_rsi > overbought:
        return "sell"
    return "hold"


def _macd_signal(
    history: pd.Series,
    _params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    if len(history) < MACD_MIN_HISTORY:
        return "hold"

    macd, macd_signal, _hist = calculate_macd(history)
    prev_diff = macd.iloc[-2] - macd_signal.iloc[-2]
    curr_diff = macd.iloc[-1] - macd_signal.iloc[-1]
    if pd.isna(prev_diff) or pd.isna(curr_diff):
        return "hold"
    if prev_diff <= 0 and curr_diff > 0:
        return "buy"
    if prev_diff >= 0 and curr_diff < 0:
        return "sell"
    return "hold"


def _breakout_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    window = int(params.get("window", 20))
    min_history = max(30, window + 1)
    if len(history) < min_history:
        return "hold"

    current_close = float(history.iloc[-1])
    if not math.isfinite(current_close):
        return "hold"
    prior_window = history.iloc[-(window + 1) : -1]
    highest_breakout = float(prior_window.max())
    lowest_breakdown = float(prior_window.min())
    if not math.isfinite(highest_breakout) or not math.isfinite(lowest_breakdown):
        return "hold"

    if current_close > highest_breakout:
        return "buy"
    if current_close < lowest_breakdown:
        return "sell"
    return "hold"


def _pullback_in_trend_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    fast_window = int(params.get("fast_window", 20))
    trend_window = int(params.get("trend_window", 50))
    pullback_pct = float(params.get("pullback_pct", 0.03))
    min_history = max(60, trend_window)
    if len(history) < min_history:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_trend = float(history.tail(trend_window).mean())

    if not math.isfinite(close) or not math.isfinite(sma_fast) or not math.isfinite(sma_trend):
        return "hold"

    if close < sma_trend:
        return "sell"

    in_uptrend = sma_fast > sma_trend
    in_pullback_zone = (sma_fast * (1.0 - pullback_pct)) <= close <= sma_fast
    if in_uptrend and in_pullback_zone:
        return "buy"
    return "hold"


def _bollinger_mean_reversion_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    window = int(params.get("window", 20))
    num_std = float(params.get("num_std", 2.0))
    min_history = max(30, window)
    if len(history) < min_history:
        return "hold"

    segment = history.tail(window)
    close = float(segment.iloc[-1])
    if not math.isfinite(close):
        return "hold"
    middle = float(segment.mean())
    std = float(segment.std(ddof=0))
    if not math.isfinite(std) or std <= 0:
        return "hold"

    lower_band = middle - (num_std * std)
    upper_band = middle + (num_std * std)
    if close < lower_band:
        return "buy"
    if close > upper_band:
        return "sell"
    return "hold"


def _ma_crossover_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    fast_window = int(params.get("fast_window", 20))
    slow_window = int(params.get("slow_window", 50))
    min_history = max(60, slow_window + 1)
    if len(history) < min_history:
        return "hold"

    fast = history.rolling(window=fast_window).mean()
    slow = history.rolling(window=slow_window).mean()
    prev_fast = float(fast.iloc[-2])
    prev_slow = float(slow.iloc[-2])
    curr_fast = float(fast.iloc[-1])
    curr_slow = float(slow.iloc[-1])

    if pd.isna(prev_fast) or pd.isna(prev_slow) or pd.isna(curr_fast) or pd.isna(curr_slow):
        return "hold"
    if not all(math.isfinite(v) for v in (prev_fast, prev_slow, curr_fast, curr_slow)):
        return "hold"

    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "buy"
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return "sell"

    # Keep this strategy actionable after a recent crossover by honoring
    # the current fast/slow stack and price confirmation.
    close = float(history.iloc[-1])
    if not math.isfinite(close):
        return "hold"
    if curr_fast > curr_slow and close >= curr_fast:
        return "buy"
    if curr_fast < curr_slow and close <= curr_fast:
        return "sell"
    return "hold"


def _volatility_filtered_trend_signal(
    history: pd.Series,
    params: StrategyParams,
    _feature_history: pd.DataFrame | None = None,
) -> str:
    fast_window = int(params.get("fast_window", 20))
    slow_window = int(params.get("slow_window", 50))
    vol_window = int(params.get("vol_window", 20))
    max_annualized_vol_pct = float(params.get("max_annualized_vol_pct", 45.0))
    min_history = max(60, slow_window, vol_window + 1)
    if len(history) < min_history:
        return "hold"

    returns = history.pct_change().dropna()
    recent_returns = returns.tail(vol_window)
    if recent_returns.empty:
        return "hold"
    annualized_vol_pct = float(recent_returns.std(ddof=0) * (TRADING_DAYS_PER_YEAR**0.5) * 100.0)
    if pd.isna(annualized_vol_pct) or annualized_vol_pct > max_annualized_vol_pct:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    if not math.isfinite(close) or not math.isfinite(sma_fast) or not math.isfinite(sma_slow):
        return "hold"
    if close > sma_fast > sma_slow:
        return "buy"
    if close < sma_fast:
        return "sell"
    return "hold"


def _topic_proxy_rotation_signal(
    history: pd.Series,
    params: StrategyParams,
    feature_history: pd.DataFrame | None = None,
) -> str:
    window = int(params.get("window", 20))
    min_history = max(40, window)
    if len(history) < min_history:
        return "hold"

    proxy_available = _feature_value(feature_history, "topic_proxy_available")
    rel_strength = _feature_value(feature_history, "topic_proxy_rel_strength")
    trend_gap = _feature_value(feature_history, "topic_proxy_trend_gap")
    if proxy_available is None or proxy_available < PROXY_AVAILABILITY_THRESHOLD or rel_strength is None or trend_gap is None:
        return "hold"

    close = float(history.iloc[-1])
    sma_mid = float(history.tail(window).mean())
    if not math.isfinite(close) or not math.isfinite(sma_mid):
        return "hold"
    min_rel_strength = float(params.get("min_rel_strength", 0.0))
    exit_rel_strength = float(params.get("exit_rel_strength", 0.0))
    min_proxy_trend_gap = float(params.get("min_proxy_trend_gap", 0.0))

    if close > sma_mid and rel_strength > min_rel_strength and trend_gap > min_proxy_trend_gap:
        return "buy"
    if close < sma_mid or rel_strength < exit_rel_strength or trend_gap < 0.0:
        return "sell"
    return "hold"


def _macro_proxy_regime_signal(
    history: pd.Series,
    params: StrategyParams,
    feature_history: pd.DataFrame | None = None,
) -> str:
    fast_window = int(params.get("fast_window", 20))
    slow_window = int(params.get("slow_window", 50))
    min_history = max(60, slow_window)
    if len(history) < min_history:
        return "hold"

    risk_on_score = _feature_value(feature_history, "macro_risk_on_score")
    vix_pressure = _feature_value(feature_history, "macro_vix_pressure")
    equity_bond_spread = _feature_value(feature_history, "macro_equity_bond_spread")
    if risk_on_score is None or vix_pressure is None or equity_bond_spread is None:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    if not math.isfinite(close) or not math.isfinite(sma_fast) or not math.isfinite(sma_slow):
        return "hold"
    min_risk_on_score = float(params.get("min_risk_on_score", 0.0))
    min_equity_bond_spread = float(params.get("min_equity_bond_spread", 0.0))
    max_vix_pressure = float(params.get("max_vix_pressure", 0.12))
    exit_risk_on_score = float(params.get("exit_risk_on_score", 0.0))

    if (
        close > sma_fast > sma_slow
        and risk_on_score >= min_risk_on_score
        and equity_bond_spread >= min_equity_bond_spread
        and vix_pressure <= max_vix_pressure
    ):
        return "buy"
    if close < sma_fast or risk_on_score < exit_risk_on_score or vix_pressure > max_vix_pressure:
        return "sell"
    return "hold"


def _policy_regime_signal(
    history: pd.Series,
    params: StrategyParams,
    feature_history: pd.DataFrame | None = None,
) -> str:
    """Policy regime signal using ETF-derived macro/political environment indicators.

    Buys when price momentum aligns with a risk-on macro environment (SPY
    outperforming defensive ETFs).  Falls back to ``"hold"`` when features
    from :class:`~trading.features.policy_feature_provider.PolicyFeatureProvider`
    are unavailable.

    Required features (from ``feature_history``):
        policy_risk_on_score   — 0–1 composite risk-on score (higher = risk-on).
        policy_defensive_tilt  — Positive when defensives outperform equities.
    """
    fast_window = int(params.get("fast_window", 20))
    slow_window = int(params.get("slow_window", 50))
    if len(history) < max(30, slow_window):
        return "hold"

    risk_on_score = _feature_value(feature_history, POLICY_RISK_ON_SCORE)
    defensive_tilt = _feature_value(feature_history, POLICY_DEFENSIVE_TILT)
    if risk_on_score is None or defensive_tilt is None:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    if not math.isfinite(close) or not math.isfinite(sma_fast) or not math.isfinite(sma_slow):
        return "hold"

    risk_on_threshold = float(params.get("risk_on_threshold", POLICY_RISK_ON_BUY_THRESHOLD))
    risk_off_threshold = float(params.get("risk_off_threshold", POLICY_RISK_OFF_SELL_THRESHOLD))
    max_defensive_tilt = float(params.get("max_defensive_tilt", POLICY_MAX_DEFENSIVE_TILT))

    if (
        close > sma_fast > sma_slow
        and risk_on_score >= risk_on_threshold
        and defensive_tilt <= max_defensive_tilt
    ):
        return "buy"
    if close < sma_slow or risk_on_score < risk_off_threshold:
        return "sell"
    return "hold"


def _news_sentiment_signal(
    history: pd.Series,
    params: StrategyParams,
    feature_history: pd.DataFrame | None = None,
) -> str:
    """News sentiment signal using VADER-scored headlines.

    Buys when price is in a short-term uptrend and recent news sentiment
    is bullish.  Sells when sentiment turns negative and price is below
    the short SMA.  Falls back to ``"hold"`` when features from
    :class:`~trading.features.news_feature_provider.NewsFeatureProvider`
    are unavailable or headline volume is too low.

    Required features (from ``feature_history``):
        news_sentiment_score  — Mean VADER compound score in [-1, 1].
        news_headline_count   — Number of headlines scored.
    """
    fast_window = int(params.get("fast_window", 10))
    slow_window = int(params.get("slow_window", 30))
    if len(history) < max(10, slow_window):
        return "hold"

    sentiment = _feature_value(feature_history, NEWS_SENTIMENT_SCORE)
    headline_count = _feature_value(feature_history, NEWS_HEADLINE_COUNT)
    if sentiment is None or headline_count is None:
        return "hold"

    min_headlines = float(params.get("min_headlines", NEWS_MIN_HEADLINES_REQUIRED))
    if headline_count < min_headlines:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    if not math.isfinite(close) or not math.isfinite(sma_fast) or not math.isfinite(sma_slow):
        return "hold"

    buy_sentiment = float(params.get("buy_sentiment", NEWS_BUY_SENTIMENT_THRESHOLD))
    sell_sentiment = float(params.get("sell_sentiment", NEWS_SELL_SENTIMENT_THRESHOLD))

    if close > sma_fast > sma_slow and sentiment >= buy_sentiment:
        return "buy"
    if close < sma_fast and sentiment <= sell_sentiment:
        return "sell"
    return "hold"


def _social_trend_rotation_signal(
    history: pd.Series,
    params: StrategyParams,
    feature_history: pd.DataFrame | None = None,
) -> str:
    """Social trend rotation signal using Google Trends interest and Reddit mentions.

    Buys when the ticker shows elevated social interest (Google Trends score)
    alongside positive Reddit sentiment and an upward price trend.  Sells
    when social interest is fading and price weakens.  Falls back to
    ``"hold"`` when features from
    :class:`~trading.features.social_feature_provider.SocialFeatureProvider`
    are unavailable.

    Required features (from ``feature_history``):
        social_trend_score      — Google Trends interest, normalised [0, 1].
        social_mention_count    — Reddit post count (float).
        social_reddit_sentiment — Mean VADER score of Reddit titles [-1, 1].
    """
    fast_window = int(params.get("fast_window", 10))
    slow_window = int(params.get("slow_window", 30))
    if len(history) < max(10, slow_window):
        return "hold"

    trend_score = _feature_value(feature_history, SOCIAL_TREND_SCORE)
    mention_count = _feature_value(feature_history, SOCIAL_MENTION_COUNT)
    reddit_sentiment = _feature_value(feature_history, SOCIAL_REDDIT_SENTIMENT)
    if trend_score is None or mention_count is None or reddit_sentiment is None:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    if not math.isfinite(close) or not math.isfinite(sma_fast) or not math.isfinite(sma_slow):
        return "hold"

    trend_threshold = float(params.get("trend_threshold", SOCIAL_TREND_BUY_THRESHOLD))
    trend_exit = float(params.get("trend_exit", SOCIAL_TREND_EXIT_THRESHOLD))
    min_reddit_sentiment = float(params.get("min_reddit_sentiment", SOCIAL_MIN_REDDIT_SENTIMENT))

    if (
        close > sma_fast > sma_slow
        and trend_score >= trend_threshold
        and reddit_sentiment >= min_reddit_sentiment
    ):
        return "buy"
    if close < sma_slow or trend_score < trend_exit:
        return "sell"
    return "hold"


STRATEGY_REGISTRY: dict[str, StrategySpec] = {
    "trend": StrategySpec(
        strategy_id="trend",
        signal_fn=_trend_signal,
        default_params={"fast_window": 10, "slow_window": 20},
        aliases=("trend_v1", "momentum"),
        description="Trend stack using close > SMA fast > SMA slow.",
        strategy_style="trend",
    ),
    "mean_reversion": StrategySpec(
        strategy_id="mean_reversion",
        signal_fn=_mean_reversion_signal,
        default_params={"window": 20, "band_pct": 0.02},
        aliases=("mean", "reversion"),
        description="Mean reversion to SMA with symmetric percentage bands.",
        strategy_style="mean_reversion",
    ),
    "rsi": StrategySpec(
        strategy_id="rsi",
        signal_fn=_rsi_signal,
        default_params={"window": RSI_DEFAULT_WINDOW, "oversold": RSI_OVERSOLD, "overbought": RSI_OVERBOUGHT},
        aliases=("rsi_strategy",),
        description="RSI threshold strategy.",
        strategy_style="mean_reversion",
    ),
    "macd": StrategySpec(
        strategy_id="macd",
        signal_fn=_macd_signal,
        default_params={},
        aliases=("macd_strategy",),
        description="MACD crossover strategy.",
        strategy_style="trend",
    ),
    "breakout": StrategySpec(
        strategy_id="breakout",
        signal_fn=_breakout_signal,
        default_params={"window": 20},
        aliases=("donchian",),
        description="Donchian-style breakout and breakdown signal.",
        strategy_style="trend",
    ),
    "pullback_trend": StrategySpec(
        strategy_id="pullback_trend",
        signal_fn=_pullback_in_trend_signal,
        default_params={"fast_window": 20, "trend_window": 50, "pullback_pct": 0.03},
        aliases=("pullback",),
        description="Buy pullbacks in a broader uptrend.",
        strategy_style="trend",
    ),
    "bollinger_mean_reversion": StrategySpec(
        strategy_id="bollinger_mean_reversion",
        signal_fn=_bollinger_mean_reversion_signal,
        default_params={"window": 20, "num_std": 2.0},
        aliases=("bollinger", "bbands"),
        description="Mean reversion using Bollinger bands.",
        strategy_style="mean_reversion",
    ),
    "ma_crossover": StrategySpec(
        strategy_id="ma_crossover",
        signal_fn=_ma_crossover_signal,
        default_params={"fast_window": 20, "slow_window": 50},
        aliases=("moving_average", "ma"),
        description="Fast/slow moving-average crossover.",
        strategy_style="trend",
    ),
    "volatility_filtered_trend": StrategySpec(
        strategy_id="volatility_filtered_trend",
        signal_fn=_volatility_filtered_trend_signal,
        default_params={
            "fast_window": 20,
            "slow_window": 50,
            "vol_window": 20,
            "max_annualized_vol_pct": 45.0,
        },
        aliases=("volatility_trend", "vol_filter_trend"),
        description="Trend signal only when recent annualized volatility is below threshold.",
        strategy_style="trend",
    ),
    "topic_proxy_rotation": StrategySpec(
        strategy_id="topic_proxy_rotation",
        signal_fn=_topic_proxy_rotation_signal,
        default_params={
            "window": 20,
            "min_rel_strength": 0.0,
            "exit_rel_strength": 0.0,
            "min_proxy_trend_gap": 0.0,
        },
        aliases=("topic_rotation", "sector_proxy_rotation", "theme_proxy"),
        description="Rotate into names backed by strong sector/theme ETF proxy relative strength.",
        required_features=("topic_proxy_rel_strength", "topic_proxy_trend_gap"),
        strategy_style="neutral",
    ),
    "macro_proxy_regime": StrategySpec(
        strategy_id="macro_proxy_regime",
        signal_fn=_macro_proxy_regime_signal,
        default_params={
            "fast_window": 20,
            "slow_window": 50,
            "min_risk_on_score": 0.0,
            "min_equity_bond_spread": 0.0,
            "max_vix_pressure": 0.12,
            "exit_risk_on_score": 0.0,
        },
        aliases=("macro_proxy", "policy_proxy", "macro_risk"),
        description="Use market-risk proxies like VIX and bond-vs-equity leadership as a macro regime filter.",
        required_features=("macro_risk_on_score", "macro_vix_pressure", "macro_equity_bond_spread"),
        strategy_style="neutral",
    ),
    "policy_regime": StrategySpec(
        strategy_id="policy_regime",
        signal_fn=_policy_regime_signal,
        default_params={
            "fast_window": 20,
            "slow_window": 50,
            "risk_on_threshold": POLICY_RISK_ON_BUY_THRESHOLD,
            "risk_off_threshold": POLICY_RISK_OFF_SELL_THRESHOLD,
            "max_defensive_tilt": POLICY_MAX_DEFENSIVE_TILT,
        },
        aliases=("policy_external", "policy_etf", "political_regime"),
        description=(
            "Buy when price momentum and ETF-derived macro regime both signal risk-on. "
            "Uses TLT/GLD/XLU/UUP vs SPY trailing returns as a policy environment proxy. "
            "Requires PolicyFeatureProvider features: policy_risk_on_score, policy_defensive_tilt."
        ),
        required_features=(POLICY_RISK_ON_SCORE, POLICY_DEFENSIVE_TILT),
        strategy_style="alternative",
    ),
    "news_sentiment": StrategySpec(
        strategy_id="news_sentiment",
        signal_fn=_news_sentiment_signal,
        default_params={
            "fast_window": 10,
            "slow_window": 30,
            "buy_sentiment": NEWS_BUY_SENTIMENT_THRESHOLD,
            "sell_sentiment": NEWS_SELL_SENTIMENT_THRESHOLD,
            "min_headlines": NEWS_MIN_HEADLINES_REQUIRED,
        },
        aliases=("news", "news_sentiment_strategy", "sentiment"),
        description=(
            "Buy when short-term price trend is up and VADER-scored news sentiment is bullish. "
            "Requires NewsFeatureProvider features: news_sentiment_score, news_headline_count."
        ),
        required_features=(NEWS_SENTIMENT_SCORE, NEWS_HEADLINE_COUNT),
        strategy_style="alternative",
    ),
    "social_trend_rotation": StrategySpec(
        strategy_id="social_trend_rotation",
        signal_fn=_social_trend_rotation_signal,
        default_params={
            "fast_window": 10,
            "slow_window": 30,
            "trend_threshold": SOCIAL_TREND_BUY_THRESHOLD,
            "trend_exit": SOCIAL_TREND_EXIT_THRESHOLD,
            "min_reddit_sentiment": SOCIAL_MIN_REDDIT_SENTIMENT,
        },
        aliases=("social", "social_trend", "reddit_trend"),
        description=(
            "Buy when Google Trends interest is elevated, Reddit sentiment is neutral-to-positive, "
            "and price is in a short-term uptrend. "
            "Requires SocialFeatureProvider features: social_trend_score, social_mention_count, "
            "social_reddit_sentiment."
        ),
        required_features=(SOCIAL_TREND_SCORE, SOCIAL_MENTION_COUNT, SOCIAL_REDDIT_SENTIMENT),
        strategy_style="alternative",
    ),
}


def available_strategy_ids() -> list[str]:
    return sorted(STRATEGY_REGISTRY.keys())


def _invalid_strategy_error(strategy_name: str) -> ValueError:
    available = ", ".join(available_strategy_ids())
    return ValueError(f"Unknown strategy '{strategy_name}'. Valid strategies: {available}")


def _resolve_exact_or_alias(name: str) -> StrategySpec | None:
    if name in STRATEGY_REGISTRY:
        return STRATEGY_REGISTRY[name]

    for spec in STRATEGY_REGISTRY.values():
        if name in spec.aliases:
            return spec

    return None


def _resolve_by_keyword(name: str) -> StrategySpec | None:
    if any(token in name for token in ("bollinger", "bbands")):
        return STRATEGY_REGISTRY["bollinger_mean_reversion"]
    if "breakout" in name or "donchian" in name:
        return STRATEGY_REGISTRY["breakout"]
    if "pullback" in name:
        return STRATEGY_REGISTRY["pullback_trend"]
    if "vol" in name and "trend" in name:
        return STRATEGY_REGISTRY["volatility_filtered_trend"]
    if "topic" in name or ("sector" in name and "rotation" in name) or "theme" in name:
        return STRATEGY_REGISTRY["topic_proxy_rotation"]
    if "policy_regime" in name or "political" in name or "policy_etf" in name:
        return STRATEGY_REGISTRY["policy_regime"]
    if "macro" in name or "policy" in name:
        return STRATEGY_REGISTRY["macro_proxy_regime"]
    if "news" in name or "sentiment" in name:
        return STRATEGY_REGISTRY["news_sentiment"]
    if "social" in name or "reddit" in name:
        return STRATEGY_REGISTRY["social_trend_rotation"]
    if "cross" in name and ("ma" in name or "moving_average" in name):
        return STRATEGY_REGISTRY["ma_crossover"]
    if "rsi" in name:
        return STRATEGY_REGISTRY["rsi"]
    if "macd" in name:
        return STRATEGY_REGISTRY["macd"]
    if "mean" in name or "reversion" in name:
        return STRATEGY_REGISTRY["mean_reversion"]
    if "trend" in name or "momentum" in name:
        return STRATEGY_REGISTRY["trend"]
    return None


def resolve_strategy(strategy_name: str) -> StrategySpec:
    """Resolve a strategy label to a registry-backed strategy specification."""
    name = strategy_name.strip().lower()
    if not name:
        raise _invalid_strategy_error(strategy_name)

    exact_match = _resolve_exact_or_alias(name)
    if exact_match is not None:
        return exact_match

    keyword_match = _resolve_by_keyword(name)
    if keyword_match is not None:
        return keyword_match

    raise _invalid_strategy_error(strategy_name)


def validate_strategy_name(strategy_name: str) -> str:
    """Validate an operator-provided strategy label and return its canonical strategy id."""
    return resolve_strategy(strategy_name).strategy_id


def resolve_signal(
    strategy_name: str,
    history: pd.Series,
    feature_history: pd.DataFrame | None = None,
) -> str:
    """Resolve strategy labels to explicit signal models used during backtesting."""
    spec = resolve_strategy(strategy_name)
    return spec.signal_fn(history, spec.default_params, feature_history)
