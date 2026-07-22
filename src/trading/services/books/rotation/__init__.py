"""Book-keyed rotation sub-package: champion/challenger rotation.

Gathers the rotation surface previously scattered across the books and profiles
services into one cohesive package:

- ``engine`` — schedule/policy resolution plus rotation evaluation and application
- ``metrics`` — rotation strategy metrics
- ``challenger_evaluation`` — challenger shadow evaluation
- ``config_parser`` — parse a profile's rotation config into ``BookRotationConfig``

Import directly from the concrete submodule (e.g.
``from trading.services.books.rotation.engine import resolve_book_rotation_schedule``).
"""

from __future__ import annotations
