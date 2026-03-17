from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def build_chart_path(ticker: str, period: str, interval: str) -> Path:
    charts_dir = Path("local/charts")
    charts_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ticker.upper()}_{period}_{interval}_{ts}.png".replace("/", "-")
    return charts_dir / filename


def plot_trends(
    df: pd.DataFrame,
    ticker: str,
    period: str,
    interval: str,
    show_chart: bool,
) -> Path:
    fig, axes = plt.subplots(
        nrows=3,
        ncols=1,
        figsize=(12, 10),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1, 2]},
    )

    ax_price, ax_volume, ax_indicators = axes

    ax_price.plot(df.index, df["Close"], label="Close", linewidth=1.4)
    ax_price.plot(df.index, df["MA20"], label="MA20", linewidth=1.0)
    ax_price.plot(df.index, df["MA50"], label="MA50", linewidth=1.0)
    ax_price.plot(df.index, df["MA200"], label="MA200", linewidth=1.0)
    ax_price.set_title(f"{ticker.upper()} Price Trend ({period}, {interval})")
    ax_price.set_ylabel("Price")
    ax_price.grid(alpha=0.25)
    ax_price.legend(loc="best")

    ax_volume.bar(df.index, df["Volume"], width=1.0, alpha=0.6, label="Volume")
    ax_volume.set_ylabel("Volume")
    ax_volume.grid(alpha=0.2)

    ax_indicators.plot(df.index, df["RSI14"], label="RSI14", linewidth=1.0)
    ax_indicators.axhline(70, color="red", linestyle="--", linewidth=0.8, alpha=0.8)
    ax_indicators.axhline(30, color="green", linestyle="--", linewidth=0.8, alpha=0.8)
    ax_indicators.set_ylabel("RSI")
    ax_indicators.set_ylim(0, 100)
    ax_indicators.grid(alpha=0.2)

    ax_macd = ax_indicators.twinx()
    colors = ["#2ca02c" if h >= 0 else "#d62728" for h in df["MACDHist"]]
    ax_macd.bar(df.index, df["MACDHist"], color=colors, alpha=0.25, label="MACD Hist")
    ax_macd.plot(df.index, df["MACD"], label="MACD", linewidth=1.0)
    ax_macd.plot(df.index, df["MACDSignal"], label="Signal", linewidth=1.0)
    ax_macd.set_ylabel("MACD")

    lines1, labels1 = ax_indicators.get_legend_handles_labels()
    lines2, labels2 = ax_macd.get_legend_handles_labels()
    ax_indicators.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    ax_indicators.set_xlabel("Date")

    latest = df.iloc[-1]
    latest_return = latest["DailyReturnPct"]
    fig.suptitle(
        f"Latest Close: {latest['Close']:.2f} | Daily Return: {latest_return:.2f}%",
        fontsize=10,
        y=0.98,
    )

    plt.tight_layout()
    chart_path = build_chart_path(ticker, period, interval)
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    if show_chart:
        plt.show()
    else:
        plt.close(fig)
    return chart_path
