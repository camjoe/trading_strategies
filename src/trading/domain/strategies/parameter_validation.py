from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from trading.domain.strategies.contracts import PrimitiveSpec
from trading.domain.strategies.registry import PRIMITIVE_CATALOG


def resolve_primitive(primitive: str) -> PrimitiveSpec:
    """Resolve a primitive name to its code spec; raises for unknown primitives."""
    spec = PRIMITIVE_CATALOG.get(primitive.strip().lower())
    if spec is None:
        available = ", ".join(sorted(PRIMITIVE_CATALOG))
        raise ValueError(f"Unknown signal primitive '{primitive}'. Valid primitives: {available}")
    return spec


def validate_params_against_primitive(primitive: str, params: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and coerce knob overrides against a primitive's knob schema.

    Rejects knob names the primitive does not define and values that cannot be
    coerced to the knob's type. Returns a new dict of the coerced overrides
    (only the provided keys); callers layer these over the primitive defaults.
    """
    spec = resolve_primitive(primitive)
    schema = spec.knob_schema
    unknown = sorted(name for name in params if name not in schema)
    if unknown:
        valid = ", ".join(sorted(schema)) or "(none)"
        raise ValueError(
            f"Unknown knob(s) for primitive '{spec.primitive}': {', '.join(unknown)}. Valid knobs: {valid}"
        )
    return {name: _coerce_knob_value(name, value, schema[name]) for name, value in params.items()}


def _coerce_knob_value(name: str, value: Any, default: Any) -> Any:
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        raise ValueError(f"Knob '{name}' expects a boolean, got {value!r}.")
    if isinstance(default, int):  # bool is handled above
        return _coerce_int_knob(name, value)
    if isinstance(default, float):
        return _coerce_float_knob(name, value)
    return value


def _coerce_int_knob(name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Knob '{name}' expects an integer, got boolean {value!r}.")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"Knob '{name}' expects an integer, got {value!r}.")
        return int(value)
    try:
        return int(str(value).strip())
    except TypeError, ValueError:
        raise ValueError(f"Knob '{name}' expects an integer, got {value!r}.") from None


def _coerce_float_knob(name: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Knob '{name}' expects a number, got boolean {value!r}.")
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except TypeError, ValueError:
        raise ValueError(f"Knob '{name}' expects a number, got {value!r}.") from None
