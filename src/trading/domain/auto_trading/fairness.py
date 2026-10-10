"""Deterministic fair ordering of equally-signalled tickers and capacity claimants.

The signal says only "buy", equally, for every candidate, so the engine has no
basis to rank them and must not let universe/file order decide. Hashing each name
with a per-run seed spreads first pick evenly across runs while staying
reproducible within a run.
"""

import hashlib
from collections.abc import Sequence


def order_signal_candidates(candidates: Sequence[str], *, seed: str) -> list[str]:
    """Order equally-signalled tickers so no name is systematically preferred.

    A run trades one candidate per book, taking the first it can size. The list
    arrives in universe order, so the earliest names in the ticker file were
    always tried first — and since a bought name stops being a buy candidate, a
    book filled up in file order. Every book with the same universe and strategy
    built the same portfolio in the same sequence, for a reason that is a
    property of the file rather than of the market.

    The signal says only "buy", equally, for all of them, so the engine has no
    basis to rank them and must not invent one. Hashing the ticker with a
    per-run *seed* spreads first pick evenly across names over successive runs,
    while staying deterministic within a run: the same seed and candidates
    always yield the same order, so a decision can be reproduced from the audit
    trail rather than merely observed.

    The guarantee is *across runs*, not across books. Callers seed with the run
    date, so every book with the same strategy and universe sees the same order
    on the same day and reaches the same pick. That is intended: two books
    running identical configurations should decide identically, and decorrelating
    them would mean any difference in their results came from this hash rather
    than from what actually differs between them (sizing, equity, risk policy).
    To make two books pick differently, vary something that matters — their
    parameters or their universe.
    """
    return sorted(candidates, key=lambda ticker: hashlib.sha256(f"{seed}:{ticker}".encode()).hexdigest())


def order_capacity_claimants(book_ids: Sequence[int], *, seed: str) -> list[int]:
    """Order an account's books so none is permanently first in line for its capacity.

    :func:`order_signal_candidates` one layer up, with the same guarantee: stable
    within a run, varied across runs. The seed is namespaced so book ids and
    tickers of the same spelling cannot collide into a shared order.
    """
    return sorted(book_ids, key=lambda book_id: hashlib.sha256(f"{seed}:book:{book_id}".encode()).hexdigest())
