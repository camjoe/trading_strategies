"""Mechanics shared by everything that reads and writes the database.

The distinction from ``infrastructure/database/`` is *getting* a connection versus
*using* one. That package owns backend selection, path/config, schema version, and
migrations — the sqlite wiring. This one owns what trading code does with a
connection once it has it: transaction scope, and the encoding of values into
columns.

It sits below the repository layer so both repository packages
(``trading/repositories/`` and ``backtesting/repositories/``) and the
services above them can import it without either borrowing from the other, and
without services reaching into ``infrastructure.database`` — which
``scripts/checks/repo/layer_check.py`` forbids.
"""
