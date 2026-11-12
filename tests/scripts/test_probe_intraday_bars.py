from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from infrastructure.market_data.demo_provider import DemoMarketDataProvider
from scripts.data_ops import probe_intraday_bars as probe
from scripts.data_ops.probe_intraday_bars import LastBar, TickerProbe

TODAY = date(2026, 10, 19)


def frame(day: date, close: float, volume: float = 1000.0) -> pd.DataFrame:
    return pd.DataFrame(
        {"close": [close - 1, close], "volume": [900.0, volume]},
        index=pd.to_datetime([day - timedelta(days=1), day]),
    )


class LiveLikeProvider:
    """A provider with a disk-style cache: the first fetch is stored and served again unless the cache is disabled."""

    def __init__(self, closes: list[float], day: date = TODAY) -> None:
        self.closes = closes
        self.day = day
        self.network_calls = 0
        self.stored: dict[str, pd.DataFrame] = {}

    def fetch_ohlcv(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        cache_off = os.environ.get("TRADING_MARKET_DATA_CACHE_DISABLED") == "1"
        if ticker in self.stored and not cache_off:
            return self.stored[ticker]
        close = self.closes[min(self.network_calls, len(self.closes) - 1)]
        self.network_calls += 1
        result = frame(self.day, close)
        if not cache_off:
            self.stored[ticker] = result
        return result


class TestParts:
    def test_last_bar_reads_the_final_row(self) -> None:
        assert probe.last_bar(frame(TODAY, 101.5, 1234)) == LastBar(TODAY, 101.5, 1234.0)

    def test_default_tickers_come_from_the_default_universe(self) -> None:
        tickers = probe.default_tickers(3)

        assert len(tickers) == 3 and all(name.isupper() for name in tickers)


class TestProbeTicker:
    def test_a_provider_that_serves_stale_cache_shows_it_and_a_moving_bar_shows_it(self) -> None:
        provider = LiveLikeProvider([100.0, 101.0, 102.0])
        slept: list[float] = []

        result = probe.probe_tickers(provider, ["AAA"], "3mo", 60, sleep=slept.append, say=lambda _line: None)[0]  # type: ignore[arg-type]

        assert slept == [60]
        assert result.first.close == 100.0  # the first network fetch
        assert result.cached == result.first
        assert result.fresh.close == 101.0  # cache off: a new network fetch
        assert result.later is not None and result.later.close == 102.0

    def test_the_cache_setting_is_restored_afterwards(self, monkeypatch) -> None:
        monkeypatch.delenv("TRADING_MARKET_DATA_CACHE_DISABLED", raising=False)

        probe.probe_tickers(LiveLikeProvider([1.0]), ["AAA"], "3mo", 0, say=lambda _line: None)  # type: ignore[arg-type]

        assert "TRADING_MARKET_DATA_CACHE_DISABLED" not in os.environ

        monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DISABLED", "0")
        probe.probe_tickers(LiveLikeProvider([1.0]), ["AAA"], "3mo", 0, say=lambda _line: None)  # type: ignore[arg-type]
        assert os.environ["TRADING_MARKET_DATA_CACHE_DISABLED"] == "0"

    def test_a_zero_wait_skips_the_last_fetch(self) -> None:
        result = probe.probe_tickers(LiveLikeProvider([1.0, 2.0]), ["AAA"], "3mo", 0, say=lambda _line: None)[0]  # type: ignore[arg-type]

        assert result.later is None


def a_probe(first: float = 100.0, cached: float = 100.0, fresh: float = 101.0, later: float | None = 102.0, day=TODAY):
    def bar(close: float) -> LastBar:
        return LastBar(day, close, 1000.0)

    return TickerProbe("AAA", bar(first), bar(cached), bar(fresh), None if later is None else bar(later))


class TestVerdicts:
    def test_an_open_session_with_a_live_bar_and_a_stale_cache(self) -> None:
        lines = probe.verdicts([a_probe()], TODAY, market_open=True)

        text = "\n".join(lines)
        assert "unfinished bar" in text
        assert "changed between two back-to-back fetches for AAA" in text
        assert "changed the last bar for 1 of 1" in text
        assert not any(line.startswith("WARNING") for line in lines)

    def test_a_closed_market_warns_first(self) -> None:
        assert probe.verdicts([a_probe()], TODAY, market_open=False)[0].startswith("WARNING: the market is closed")

    def test_no_bar_dated_today_is_reported(self) -> None:
        text = "\n".join(probe.verdicts([a_probe(day=date(2026, 10, 16))], TODAY, market_open=True))

        assert "0 of 1 tickers (no unfinished bar was returned)" in text

    def test_agreeing_cache_and_a_bar_that_did_not_move(self) -> None:
        text = "\n".join(probe.verdicts([a_probe(cached=101.0, fresh=101.0, later=101.0)], TODAY, market_open=True))

        assert "no ticker (a quiet moment" in text
        assert "changed the last bar for 0 of 1" in text

    def test_without_a_wait_there_is_no_movement_line(self) -> None:
        text = "\n".join(probe.verdicts([a_probe(later=None)], TODAY, market_open=True))

        assert "after the wait" not in text


class TestMain:
    def test_it_prints_the_table_and_the_conclusions(self, capsys, monkeypatch) -> None:
        monkeypatch.delenv("TRADING_MARKET_DATA_CACHE_DIR", raising=False)

        code = probe.main(["--tickers", "aaa,bbb", "--wait-seconds", "0"], LiveLikeProvider([1.0, 2.0]))  # type: ignore[arg-type]

        out = capsys.readouterr().out
        assert code == 0
        assert "Probing AAA, BBB" in out and "AAA" in out and "BBB" in out
        assert "Today's bar in a fresh fetch" in out and "back-to-back fetches" in out

    def test_it_uses_a_temporary_cache_directory(self, monkeypatch) -> None:
        seen: list[str] = []

        class Recording(LiveLikeProvider):
            def fetch_ohlcv(self, ticker, period, interval):
                seen.append(os.environ["TRADING_MARKET_DATA_CACHE_DIR"])
                return super().fetch_ohlcv(ticker, period, interval)

        monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", "somewhere/real")

        probe.main(["--tickers", "AAA", "--wait-seconds", "0"], Recording([1.0]))  # type: ignore[arg-type]

        assert seen and all(path != "somewhere/real" for path in seen)
        assert os.environ["TRADING_MARKET_DATA_CACHE_DIR"] == "somewhere/real"

    def test_no_tickers_is_an_error(self, capsys, monkeypatch) -> None:
        monkeypatch.setattr(probe, "default_tickers", lambda _count: [])

        assert probe.main(["--wait-seconds", "0"], LiveLikeProvider([1.0])) == 1  # type: ignore[arg-type]
        assert "No tickers" in capsys.readouterr().err


class TestWaitsOnce:
    def test_several_tickers_share_one_wait_and_each_gets_a_later_fetch(self) -> None:
        slept: list[float] = []
        said: list[str] = []

        results = probe.probe_tickers(
            LiveLikeProvider([1.0, 2.0, 3.0, 4.0]),
            ["AAA", "BBB", "CCC"],
            "3mo",
            90,
            sleep=slept.append,
            say=said.append,  # type: ignore[arg-type]
        )

        assert slept == [90]
        assert [r.ticker for r in results] == ["AAA", "BBB", "CCC"] and all(r.later is not None for r in results)
        assert [line for line in said if line.startswith("Fetching")] == [
            "Fetching AAA ...",
            "Fetching BBB ...",
            "Fetching CCC ...",
        ]
        assert sum("Waiting 90 seconds, once" in line for line in said) == 1

    def test_no_wait_means_no_wait_message_and_no_later_fetch(self) -> None:
        said: list[str] = []

        results = probe.probe_tickers(LiveLikeProvider([1.0]), ["AAA", "BBB"], "3mo", 0, say=said.append)  # type: ignore[arg-type]

        assert all(r.later is None for r in results) and not any("Waiting" in line for line in said)


class TestMarketHours:
    def run(self, capsys, moment: datetime) -> str:
        probe.main(["--tickers", "AAA", "--wait-seconds", "0"], LiveLikeProvider([1.0, 2.0]), now=lambda: moment)  # type: ignore[arg-type]
        return capsys.readouterr().out

    def test_a_holiday_midday_gets_the_closed_warning(self, capsys) -> None:
        out = self.run(capsys, datetime(2026, 11, 26, 15, 0, tzinfo=timezone.utc))  # Thanksgiving, 10:00 Eastern

        assert "WARNING: the market is closed" in out

    def test_a_session_midday_gets_no_warning(self, capsys) -> None:
        out = self.run(capsys, datetime(2026, 10, 28, 18, 0, tzinfo=timezone.utc))  # Wednesday, 14:00 Eastern

        assert "WARNING" not in out


class PerTickerProvider:
    def __init__(self, closes: dict[str, float]) -> None:
        self.closes = closes

    def fetch_ohlcv(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        return frame(TODAY, self.closes[ticker])


class TestPerTicker:
    def test_each_result_carries_its_own_ticker_bars(self) -> None:
        provider = PerTickerProvider({"AAA": 10.0, "BBB": 20.0})

        results = probe.probe_tickers(provider, ["AAA", "BBB"], "3mo", 1, sleep=lambda _s: None, say=lambda _l: None)  # type: ignore[arg-type]

        assert {r.ticker: (r.first.close, r.fresh.close, r.later.close) for r in results if r.later} == {
            "AAA": (10.0, 10.0, 10.0),
            "BBB": (20.0, 20.0, 20.0),
        }


class TestDemoProvider:
    def test_a_demo_provider_is_flagged(self, capsys) -> None:
        class Demo(DemoMarketDataProvider):
            def fetch_ohlcv(self, ticker, period, interval):
                return frame(TODAY, 1.0)

        probe.main(["--tickers", "AAA", "--wait-seconds", "0"], Demo())

        assert "the demo provider generated these bars" in capsys.readouterr().out

    def test_a_real_provider_is_not_flagged(self, capsys) -> None:
        probe.main(["--tickers", "AAA", "--wait-seconds", "0"], LiveLikeProvider([1.0]))  # type: ignore[arg-type]

        assert "demo provider" not in capsys.readouterr().out
