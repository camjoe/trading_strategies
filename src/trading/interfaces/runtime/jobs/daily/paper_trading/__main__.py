"""Entrypoint shim: `python -m trading.interfaces.runtime.jobs.daily.paper_trading`."""

from __future__ import annotations

from trading.interfaces.runtime.jobs.daily.paper_trading import main

if __name__ == "__main__":
    raise SystemExit(main())
