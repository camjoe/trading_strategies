"""Shared order-submission service (clean book schema).

Owns the single submit → persist → on-fill path for every book (default-book
accounts and sleeved books alike), plus the injected pre-submit gate seam. See
the P4/2a work order in git history for design rationale.
"""
