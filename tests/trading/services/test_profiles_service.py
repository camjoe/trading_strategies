from __future__ import annotations

import pytest

import trading.services.profiles_service as profiles_service
from trading.models.rotation_config import RotationConfig


def test_apply_account_profiles_rejects_unknown_strategy_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        profiles_service,
        "create_account",
        lambda *args, **kwargs: create_calls.append((args, kwargs)),
    )

    with pytest.raises(ValueError, match="Unknown strategy 'mystery_strategy'"):
        profiles_service.apply_account_profiles(
            object(),
            [{"name": "acct", "strategy": "mystery_strategy"}],
            create_missing=True,
        )

    assert create_calls == []


def test_rotation_config_rejects_unknown_schedule_strategy_name() -> None:
    with pytest.raises(
        ValueError,
        match="rotation_schedule\\[0\\]: Unknown strategy 'mystery_strategy'",
    ):
        RotationConfig.from_profile(
            {
                "rotation_schedule": ["mystery_strategy", "trend"],
            }
        )
