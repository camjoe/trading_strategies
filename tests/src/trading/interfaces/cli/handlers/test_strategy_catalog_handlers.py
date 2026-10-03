from __future__ import annotations

import types

import pytest

import trading.interfaces.cli.handlers.strategy_catalog_handlers as module
from tests.src.trading.interfaces.cli.handlers.helpers import fake_parser, make_ctx, patch_services
from trading.interfaces.cli.handlers.strategy_catalog_handlers import (
    handle_configure_strategy,
    handle_create_strategy_variant,
    handle_freeze_strategy,
)


def _record(**overrides):
    base = {
        "strategy_key": "trend_fast",
        "primitive": "trend",
        "params_json": "{}",
        "status": "draft",
        "enabled": 1,
    }
    base.update(overrides)
    return types.SimpleNamespace(**base)


def test_handle_create_variant_passes_knob_overrides(capsys, monkeypatch) -> None:
    calls: dict = {}

    def _create(_conn, **kwargs):
        calls.update(kwargs)
        return _record(params_json='{"fast_window": 5}')

    patch_services(monkeypatch, module, create_strategy_variant=_create)
    handle_create_strategy_variant(
        object(),
        types.SimpleNamespace(strategy="trend_fast", primitive="trend", set_knobs=[("fast_window", "5")]),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert calls["primitive"] == "trend"
    assert calls["params"] == {"fast_window": "5"}
    assert "Created strategy trend_fast" in capsys.readouterr().out


def test_handle_configure_requires_a_change() -> None:
    with pytest.raises(SystemExit):
        handle_configure_strategy(
            object(),
            types.SimpleNamespace(strategy="trend_fast"),
            fake_parser(),
            ctx=make_ctx(),
        )


def test_handle_configure_passes_enabled_without_params(capsys, monkeypatch) -> None:
    calls: dict = {}

    def _configure(_conn, **kwargs):
        calls.update(kwargs)
        return _record(enabled=0)

    patch_services(monkeypatch, module, configure_strategy=_configure)
    handle_configure_strategy(
        object(),
        types.SimpleNamespace(strategy="trend_fast", enabled=False),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert calls["enabled"] is False
    assert calls["params"] is None
    assert "Updated strategy trend_fast" in capsys.readouterr().out


def test_handle_freeze_prints_status(capsys, monkeypatch) -> None:
    def _freeze(_conn, **_kwargs):
        return _record(status="frozen")

    patch_services(monkeypatch, module, freeze_strategy=_freeze)
    handle_freeze_strategy(
        object(),
        types.SimpleNamespace(strategy="trend_fast"),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert "Froze strategy trend_fast: status=frozen" in capsys.readouterr().out
