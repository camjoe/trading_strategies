"""Guard against order-dependent circular imports between service packages.

`services.evaluation` and `services.reporting` previously formed a latent cycle
(bridged by a backtesting facade re-export) that only survived the full suite
because collection order imported one side first. Importing each entry point in
a fresh interpreter catches a regression regardless of in-process import order.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

# Entry points that each independently enter the evaluation/reporting/backtesting
# subgraph; importing any of them first must not raise a circular ImportError.
IMPORT_ENTRYPOINTS = [
    "trading.services.evaluation",
    "trading.services.reporting",
    "trading.services.promotion.actions",
    "trading.backtesting",
    "trading.backtesting.domain.metrics",
]


@pytest.mark.parametrize("module", IMPORT_ENTRYPOINTS)
def test_module_imports_in_fresh_interpreter(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Importing {module} failed:\n{result.stderr}"
