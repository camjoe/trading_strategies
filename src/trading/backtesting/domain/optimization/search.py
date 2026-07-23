from __future__ import annotations

from itertools import product
from typing import Any

from trading.domain.exceptions import ValidationError


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
