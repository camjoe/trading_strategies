from __future__ import annotations

import hashlib
from itertools import product
from typing import Any

from trading.domain.exceptions import ValidationError
from trading.persistence.json_columns import dumps_json_column


def canonical_params_json(params: dict[str, Any]) -> str:
    """Serialize a candidate's parameters to a stable, comparable JSON string.

    Keys are sorted so the same parameter set always yields the same text — the
    canonical form persisted on a trial row and hashed by :func:`params_fingerprint`.
    """
    return dumps_json_column(params)


def params_fingerprint(params: dict[str, Any]) -> str:
    """Return a stable content hash of a candidate's parameters.

    Hashes the canonical JSON form, so two equal parameter sets collide by design —
    the basis for the one-candidate-per-window uniqueness constraint on trials.
    """
    return hashlib.sha256(canonical_params_json(params).encode("utf-8")).hexdigest()


def generate_candidates(search_space: dict[str, list[Any]], *, budget: int) -> list[dict[str, Any]]:
    """Expand a bounded search space into an ordered, deterministic candidate list.

    Parameter names are sorted and the Cartesian product is emitted in that canonical
    order, so candidate indices are stable across runs. A product larger than ``budget``
    is rejected (never silently truncated) so a run always evaluates every candidate.
    """
    if not search_space:
        raise ValidationError("search_space must define at least one parameter.")

    names = sorted(search_space)
    value_lists: list[list[Any]] = []
    total = 1
    for name in names:
        values = list(search_space[name])
        if not values:
            raise ValidationError(f"search_space['{name}'] must have at least one value.")
        value_lists.append(values)
        total *= len(values)

    if total > budget:
        raise ValidationError(
            f"Grid Cartesian product ({total}) exceeds candidate budget ({budget}). "
            "Narrow the search space or raise the budget."
        )

    return [dict(zip(names, combo)) for combo in product(*value_lists)]
