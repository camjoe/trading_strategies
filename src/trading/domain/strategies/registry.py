from __future__ import annotations

from common.constants import RSI_DEFAULT_WINDOW, RSI_OVERBOUGHT, RSI_OVERSOLD
from trading.domain.feature_provider import (
    NEWS_BUY_SENTIMENT_THRESHOLD,
    NEWS_HEADLINE_COUNT,
    NEWS_MIN_HEADLINES_REQUIRED,
    NEWS_SELL_SENTIMENT_THRESHOLD,
    NEWS_SENTIMENT_SCORE,
    POLICY_DEFENSIVE_TILT,
    POLICY_MAX_DEFENSIVE_TILT,
    POLICY_RISK_OFF_SELL_THRESHOLD,
    POLICY_RISK_ON_BUY_THRESHOLD,
    POLICY_RISK_ON_SCORE,
    SOCIAL_MENTION_COUNT,
    SOCIAL_MIN_REDDIT_SENTIMENT,
    SOCIAL_REDDIT_SENTIMENT,
    SOCIAL_TREND_BUY_THRESHOLD,
    SOCIAL_TREND_EXIT_THRESHOLD,
    SOCIAL_TREND_SCORE,
)
from trading.domain.strategies.contracts import PrimitiveSpec, StrategySpec
from trading.domain.strategies.signals.alternative import (
    _macro_proxy_regime_signal,
    _news_sentiment_signal,
    _policy_regime_signal,
    _social_trend_rotation_signal,
    _topic_proxy_rotation_signal,
)
from trading.domain.strategies.signals.technical import (
    _bollinger_mean_reversion_signal,
    _breakout_signal,
    _ma_crossover_signal,
    _macd_signal,
    _mean_reversion_signal,
    _pullback_in_trend_signal,
    _rsi_signal,
    _trend_signal,
    _volatility_filtered_trend_signal,
)


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


# One primitive per registered signal function today; keyed by the registry
# strategy id, which doubles as the primitive name for the seeded catalog.
PRIMITIVE_CATALOG: dict[str, PrimitiveSpec] = {
    spec.strategy_id: PrimitiveSpec(
        primitive=spec.strategy_id,
        signal_fn=spec.signal_fn,
        knob_schema=dict(spec.default_params),
        style=spec.strategy_style,
        required_features=spec.required_features,
        description=spec.description,
    )
    for spec in STRATEGY_REGISTRY.values()
}
