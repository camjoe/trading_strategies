"""Alternative strategy feature providers.

This package contains external-data feature providers used by
``strategy_style = "alternative"`` strategies.  All external API calls,
caching, and data normalisation live here — signal functions in
``trading/backtesting/domain/strategy_signals.py`` must never call
external services directly.

Submodules (added per phase):
    base                 — ExternalFeatureProvider ABC and ExternalFeatureBundle
    policy_feature_provider  — Phase 2: ETF proxy + Fed/FRED policy signals
    news_feature_provider    — Phase 3: news headline sentiment via VADER
    social_feature_provider  — Phase 4: Reddit + Google Trends momentum
"""
