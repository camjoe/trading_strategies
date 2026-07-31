# Retired Strategy Primitives

Type: notes
Status: Active
Created: 2026-07-30
Last Reviewed: 2026-07-30
Purpose: Preserve the decision rules and default thresholds of six strategy primitives removed from the registry, so any of them can be rebuilt from this document alone.
Related: [Strategies](strategies.md), [Backtesting](backtesting.md), [Architecture Conventions](../architecture/architecture-conventions.md)

Six primitives were removed on 2026-07-30. None had a `strategies` catalog row, so none could be
assigned to a book, rotated into, or promoted, and none had ever produced a backtest run. They were
removed ahead of a change to the signal contract, where each surviving primitive costs a migration
and permanent maintenance.

**What was removed:** the signal functions, their registry entries, their alias branches, and their
tests.

**What was kept:** every provider behind them — `ProxyFeatureDataProvider`
(`src/trading/services/market_data/features.py`), the three external providers in
`src/infrastructure/feature_providers/`, the `ExternalFeatureProvider` base class with its
caching/TTL/graceful-degradation contract, and the feature-key constants in
`src/trading/domain/feature_provider.py`. The capability is intact; only the thin signal layer went.
Those providers now have no consumer, which is a separate decision from this one.

Recreating any primitive below means writing a `SignalFunction` — `(history, params,
feature_history) -> "buy" | "sell" | "hold"` — and adding a `StrategySpec` to
`src/trading/domain/strategies/registry.py`. Note that the signal contract is expected to change;
rebuild against whatever contract is current rather than copying the shapes verbatim.

## macd

Removed for a different reason from the other five: `default_params` was `{}` and the function
ignored its `params` argument entirely. With no tunable knobs the walk-forward optimizer had nothing
to search, so the primitive could never participate in the optimize→promote loop.

- **Aliases:** `macd_strategy`
- **Style:** trend
- **Features required:** none
- **Parameters:** none

Rule, using the shared MACD helper (`calculate_macd` in `src/trading/domain/indicators.py`, which
remains):

```
if len(history) < MACD_MIN_HISTORY:            hold
macd, signal, _ = calculate_macd(history)      # EWM spans 12 / 26, signal span 9
prev_diff = macd[-2] - signal[-2]
curr_diff = macd[-1] - signal[-1]
if either diff is NaN:                         hold
if prev_diff <= 0 and curr_diff > 0:           buy      # crossing up
if prev_diff >= 0 and curr_diff < 0:           sell     # crossing down
otherwise:                                     hold
```

## The five feature-gated primitives

All five shared one template. Only the feature gate in the middle differed:

```
if len(history) < <gate>:                              hold
read the required features; if any is missing:         hold
close     = history[-1]
sma_fast  = mean(history[-fast_window:])
sma_slow  = mean(history[-slow_window:])
if any of those is non-finite:                         hold
price_trend_is_bullish = close > sma_fast > sma_slow
if price_trend_is_bullish and <buy gate>:              buy
if <exit gate>:                                        sell
otherwise:                                             hold
```

A feature value counts as missing when the column is absent, the series is empty, or the latest
value is NaN or infinite — non-finite inputs were never allowed to drive a decision.

### topic_proxy_rotation

Rotate into names backed by strong sector/theme ETF proxy relative strength. Features are
price-derived by `ProxyFeatureDataProvider` from sector ETFs — no external API.

- **Aliases:** `topic_rotation`, `sector_proxy_rotation`, `theme_proxy`
- **Style:** neutral
- **Features:** `topic_proxy_available`, `topic_proxy_rel_strength`, `topic_proxy_trend_gap`
- **Parameters:** `window` 20, `min_rel_strength` 0.0, `exit_rel_strength` 0.0, `min_proxy_trend_gap` 0.0

Deviates from the template — it uses a single mid SMA rather than a fast/slow pair, and gates on a
data-availability score first:

```
gate: len(history) < max(40, window)
if topic_proxy_available < 0.5:                        hold   # PROXY_AVAILABILITY_THRESHOLD
sma_mid = mean(history[-window:])
buy:  close > sma_mid and rel_strength > min_rel_strength and trend_gap > min_proxy_trend_gap
sell: close < sma_mid or rel_strength < exit_rel_strength or trend_gap < 0.0
```

### macro_proxy_regime

Use market-risk proxies (VIX, bond-vs-equity leadership) as a macro regime filter. Features are
price-derived from SPY / TLT / ^VIX — no external API.

- **Aliases:** `macro_proxy`, `policy_proxy`, `macro_risk`
- **Style:** neutral
- **Features:** `macro_risk_on_score`, `macro_vix_pressure`, `macro_equity_bond_spread`
- **Parameters:** `fast_window` 20, `slow_window` 50, `min_risk_on_score` 0.0,
  `min_equity_bond_spread` 0.0, `max_vix_pressure` 0.12, `exit_risk_on_score` 0.0

```
gate: len(history) < max(60, slow_window)
buy:  price_trend_is_bullish
      and risk_on_score >= min_risk_on_score
      and equity_bond_spread >= min_equity_bond_spread
      and vix_pressure <= max_vix_pressure
sell: close < sma_fast or risk_on_score < exit_risk_on_score or vix_pressure > max_vix_pressure
```

### policy_regime

Buy when price momentum and an ETF-derived macro regime both signal risk-on, using TLT/GLD/XLU/UUP
versus SPY trailing returns as a policy-environment proxy.

- **Aliases:** `policy_external`, `policy_etf`, `political_regime`
- **Style:** alternative
- **Features:** `policy_risk_on_score`, `policy_defensive_tilt` (from `PolicyFeatureProvider`)
- **Parameters:** `fast_window` 20, `slow_window` 50, `risk_on_threshold` 0.55,
  `risk_off_threshold` 0.45, `max_defensive_tilt` 0.02

```
gate: len(history) < max(30, slow_window)
buy:  price_trend_is_bullish
      and risk_on_score >= risk_on_threshold
      and defensive_tilt <= max_defensive_tilt
sell: close < sma_slow or risk_on_score < risk_off_threshold
```

### news_sentiment

Buy when a short-term price uptrend coincides with bullish VADER-scored news sentiment.

- **Aliases:** `news`, `news_sentiment_strategy`, `sentiment`
- **Style:** alternative
- **Features:** `news_sentiment_score` (mean VADER compound, [-1, 1]), `news_headline_count`
  (from `NewsFeatureProvider`)
- **Parameters:** `fast_window` 10, `slow_window` 30, `buy_sentiment` 0.10, `sell_sentiment` -0.10,
  `min_headlines` 3.0

Adds a sample-size gate — thin headline coverage holds rather than trading on one story:

```
gate: len(history) < max(10, slow_window)
if headline_count < min_headlines:                     hold
buy:  price_trend_is_bullish and sentiment >= buy_sentiment
sell: close < sma_fast and sentiment <= sell_sentiment
```

Note the sell is a conjunction here, unlike the others — sentiment alone never forced an exit.

### social_trend_rotation

Buy when Google Trends interest is elevated, Reddit sentiment is neutral-to-positive, and price is in
a short-term uptrend.

- **Aliases:** `social`, `social_trend`, `reddit_trend`
- **Style:** alternative
- **Features:** `social_trend_score` (Trends interest, normalised [0, 1]), `social_mention_count`
  (Reddit post count), `social_reddit_sentiment` (mean VADER of Reddit titles, [-1, 1])
  (from `SocialFeatureProvider`)
- **Parameters:** `fast_window` 10, `slow_window` 30, `trend_threshold` 0.40, `trend_exit` 0.20,
  `min_reddit_sentiment` -0.05

```
gate: len(history) < max(10, slow_window)
buy:  price_trend_is_bullish
      and trend_score >= trend_threshold
      and reddit_sentiment >= min_reddit_sentiment
sell: close < sma_slow or trend_score < trend_exit
```

`social_mention_count` was read and required to be present, but no threshold was applied to it.

## Evaluation caveat

None of these primitives was ever backtested in this repository, so nothing here carries evidence of
an edge — the rules and thresholds are recorded as *what the code did*, not as parameters that were
validated against out-of-sample data. Anything rebuilt from this document starts with no track
record and should go through the same walk-forward and promotion-gate process as any new strategy.
