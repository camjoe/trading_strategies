from __future__ import annotations

import pytest

from trading.models.account_config import AccountConfig
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


def test_account_config_from_mapping_coerces_known_fields_only() -> None:
    config = AccountConfig.from_mapping(
        {
            "descriptive_name": "  Growth  ",
            "learning_enabled": 1,
            "trade_size_pct": "12.5",
            "ignored_field": "ignored",
        }
    )

    assert config.descriptive_name == "  Growth  "
    assert config.learning_enabled is True
    assert config.trade_size_pct == pytest.approx(12.5)
    assert not AccountConfig.has_any_field({"rotation_enabled": True, "unknown": 1})
