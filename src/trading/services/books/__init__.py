"""Multi-book trading services package.

Book state lives in the flat modules here (assignments, sector config, helpers);
rotation and challenger shadow evaluation live in the ``rotation`` sub-package;
book-keyed intent generation lives in ``trading.services.execution.selection``.

Import concrete symbols directly from their owning module — this package exposes
no re-export facade (nothing consumed one).
"""

from __future__ import annotations
