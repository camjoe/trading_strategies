"""Tests for trading.services.universe."""

from __future__ import annotations

from pathlib import Path

import pytest

from trading.domain.exceptions import ValidationError
from trading.services.universe import (
    default_trade_symbols,
    list_available_universes,
    resolve_named_universes,
    resolve_trade_symbols,
)


def _write_universe(tmp_path: Path, name: str, tickers: list[str]) -> None:
    (tmp_path / f"{name}.txt").write_text("\n".join(tickers) + "\n", encoding="utf-8")


def test_resolve_single_universe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_universe(tmp_path, "large_cap", ["AAPL", "MSFT", "NVDA"])
    monkeypatch.setattr("trading.services.universe.TRADE_UNIVERSES_DIR", tmp_path)

    result = resolve_named_universes(["large_cap"])

    assert result == ["AAPL", "MSFT", "NVDA"]


def test_resolve_multiple_universes_union(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_universe(tmp_path, "large_cap", ["AAPL", "MSFT"])
    _write_universe(tmp_path, "growth", ["NVDA", "MSFT", "CRWD"])
    monkeypatch.setattr("trading.services.universe.TRADE_UNIVERSES_DIR", tmp_path)

    result = resolve_named_universes(["large_cap", "growth"])

    assert result == ["AAPL", "MSFT", "NVDA", "CRWD"]


def test_resolve_deduplicates_preserving_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_universe(tmp_path, "a", ["TSLA", "AMZN"])
    _write_universe(tmp_path, "b", ["AMZN", "GOOGL"])
    monkeypatch.setattr("trading.services.universe.TRADE_UNIVERSES_DIR", tmp_path)

    result = resolve_named_universes(["a", "b"])

    assert result == ["TSLA", "AMZN", "GOOGL"]
    assert result.count("AMZN") == 1


def test_resolve_raises_for_unknown_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_universe(tmp_path, "large_cap", ["AAPL"])
    monkeypatch.setattr("trading.services.universe.TRADE_UNIVERSES_DIR", tmp_path)

    with pytest.raises(FileNotFoundError, match="Universe 'bogus' not found"):
        resolve_named_universes(["large_cap", "bogus"])


def test_resolve_raises_for_empty_names() -> None:
    with pytest.raises(ValueError, match="At least one universe name"):
        resolve_named_universes([])


def test_list_available_universes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_universe(tmp_path, "large_cap", ["AAPL"])
    _write_universe(tmp_path, "growth", ["NVDA"])
    (tmp_path / "notes.md").write_text("ignored", encoding="utf-8")
    monkeypatch.setattr("trading.services.universe.TRADE_UNIVERSES_DIR", tmp_path)

    result = list_available_universes()

    assert result == ["growth", "large_cap"]


def test_list_available_universes_missing_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "trading.services.universe.TRADE_UNIVERSES_DIR",
        tmp_path / "nonexistent",
    )

    assert list_available_universes() == []


def test_resolve_ignores_comments_and_blanks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "mixed.txt").write_text(
        "# comment\nAAPL\n\nMSFT\n# another\nGOOGL\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("trading.services.universe.TRADE_UNIVERSES_DIR", tmp_path)

    result = resolve_named_universes(["mixed"])

    assert result == ["AAPL", "MSFT", "GOOGL"]


def test_resolve_trade_symbols_reports_an_unknown_name_as_a_validation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write paths need a caller-facing failure, not a FileNotFoundError."""
    _write_universe(tmp_path, "growth", ["NVDA"])
    monkeypatch.setattr("trading.services.universe.TRADE_UNIVERSES_DIR", tmp_path)

    assert resolve_trade_symbols(["growth"]) == ["NVDA"]
    with pytest.raises(ValidationError, match="Universe 'bogus' not found"):
        resolve_trade_symbols(["bogus"])
    with pytest.raises(ValidationError, match="At least one universe name"):
        resolve_trade_symbols([])


def test_default_trade_symbols_expands_the_default_universe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_universe(tmp_path, "default", ["AAPL", "MSFT"])
    monkeypatch.setattr("trading.services.universe.TRADE_UNIVERSES_DIR", tmp_path)

    assert default_trade_symbols() == ["AAPL", "MSFT"]
