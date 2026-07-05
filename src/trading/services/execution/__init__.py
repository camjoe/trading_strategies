"""Shared order-submission service (clean book schema).

Owns the single submit → persist → on-fill path for every book (default-book
accounts and sleeved books alike), plus the injected pre-submit gate seam. See
``docs/implementation/p4-convergence.md`` (P4 / 2a).
"""
