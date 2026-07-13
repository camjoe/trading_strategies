from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel

from .mappings import ACCOUNT_CONFIG_API_FIELDS, ROTATION_API_FIELDS, TEXT_API_FIELDS
from .models import AccountParamsUpdateCommand, AdminCreateAccountCommand, ApiFieldMapping


def _clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value))


def _dump_model(model: BaseModel, *, exclude_none: bool) -> dict[str, object]:
    return dict(model.model_dump(exclude_none=exclude_none))


def _map_api_values(
    values: Mapping[str, object],
    field_mappings: tuple[ApiFieldMapping, ...],
) -> dict[str, object]:
    mapped: dict[str, object] = {}
    for field in field_mappings:
        if field.api_name not in values:
            continue
        value = values[field.api_name]
        if field.api_name in TEXT_API_FIELDS:
            value = _clean_text(value)
        mapped[field.storage_name] = value
    return mapped


def _map_rotation_settings(values: Mapping[str, object]) -> dict[str, object]:
    """Convert the nested camelCase ``rotation`` object to the profile shape."""
    raw = values.get("rotation")
    if not isinstance(raw, Mapping):
        return {}
    return _map_api_values(raw, ROTATION_API_FIELDS)


def build_admin_create_account_command(payload: BaseModel) -> AdminCreateAccountCommand:
    values = _dump_model(payload, exclude_none=True)
    return AdminCreateAccountCommand(
        name=str(values["name"]).strip(),
        strategy=str(values["strategy"]).strip(),
        initial_cash=_coerce_float(values["initialCash"]),
        benchmark_ticker=str(values.get("benchmarkTicker", "SPY")).strip().upper() or "SPY",
        config_values=_map_api_values(values, ACCOUNT_CONFIG_API_FIELDS),
        rotation_settings=_map_rotation_settings(values),
    )


def build_account_params_update_command(body: BaseModel) -> AccountParamsUpdateCommand:
    values = _dump_model(body, exclude_none=True)
    strategy_value = values.get("strategy")
    return AccountParamsUpdateCommand(
        strategy=_clean_text(strategy_value) if strategy_value is not None else None,
        config_values=_map_api_values(values, ACCOUNT_CONFIG_API_FIELDS),
        rotation_settings=_map_rotation_settings(values),
    )
