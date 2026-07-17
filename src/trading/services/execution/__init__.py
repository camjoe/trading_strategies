"""Shared order-submission service (clean book schema).

Owns the single submit → persist → on-fill path for every book, plus the
injected pre-submit gate seam.
"""
