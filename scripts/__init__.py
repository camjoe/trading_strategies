"""Scripts package.

The ``apps/`` and ``src/`` packages (``infrastructure``, ``paper_trading_web``,
``trends``) are made importable by the project's editable install
(``pip install -e .`` — see pyproject.toml), so no sys.path bootstrap is needed
here.  ``trading``/``common`` resolve via the repo root, which is already on the
path when scripts are run with ``python -m scripts.<name>``.
"""
