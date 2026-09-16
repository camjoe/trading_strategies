from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

# How a real-data scenario turns one frozen fixture into paths.
# replay serves the fixture as one deterministic path; bootstrap block-resamples
# it into many paths, so its per-cell result is a distribution like a synthetic one.
SCENARIO_MODE_REPLAY = "replay"
SCENARIO_MODE_BOOTSTRAP = "bootstrap"


@dataclass(frozen=True)
class FixtureSource:
    """A real-data scenario's binding to a frozen fixture.

    The registry entry only names the fixture and the mode; the composition seam
    loads the fixture from ``local/`` and binds a concrete generator, because
    reading a file is I/O and must not happen in the domain or at import time.
    ``block_size`` is the moving-block length in trading days, for bootstrap only.
    """

    fixture_id: str
    mode: str
    block_size: int = 0


@dataclass(frozen=True)
class PathRequest:
    """The inputs a generator needs to build one path's bar-set.

    ``seed`` is the per-path seed the runner derives from a scenario's base seed
    and the path index, so path N of a scenario always rebuilds identically.
    ``tickers`` includes the benchmark: the runner asks for it in the same call so
    the benchmark shares the path's regime.
    """

    index: pd.DatetimeIndex
    tickers: tuple[str, ...]
    seed: int
    params: Mapping[str, Any]


# A generator turns one PathRequest into a bar frame per requested ticker. Each
# frame is indexed by ``request.index`` and carries BAR_COLUMNS. The callable is
# the polymorphism point: a synthetic regime, a bootstrap, or a replay are all
# just different generators behind this one signature.
PathGenerator = Callable[[PathRequest], dict[str, pd.DataFrame]]


@dataclass(frozen=True)
class ScenarioSpec:
    """One named market condition the bench can run strategies through.

    A scenario yields ``path_count`` bar-sets from ``generator`` over a window of
    ``days`` trading days. ``path_count`` above one is a Monte Carlo scenario whose
    per-cell result is a distribution; a future replay scenario sets it to one.
    """

    scenario_id: str
    generator: PathGenerator
    params: Mapping[str, Any]
    path_count: int
    tickers: tuple[str, ...]
    benchmark: str
    base_seed: int
    days: int
    description: str = ""
    aliases: tuple[str, ...] = ()
    # Set on a real-data scenario. When present, the composition seam loads the
    # named fixture, binds a replay/bootstrap generator over it, and (for replay)
    # overrides ``days`` with the fixture's own length. ``generator`` on such a
    # spec is the unbound sentinel and is never called directly.
    source: FixtureSource | None = None
