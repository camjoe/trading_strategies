"""Shared test helpers for all tests/trading/interfaces/ subtrees."""

from __future__ import annotations

import runpy
import sys


def run_module_as_main(module_name: str) -> None:
    """Run a module as __main__, suppressing the double-import RuntimeWarning.

    Interface test files import a module at the top level (so other tests can
    call module functions) and also run it as __main__ to smoke-test the
    entrypoint wiring.  When the module is already in sys.modules, a bare
    runpy.run_module call triggers:

        '<module>' found in sys.modules after import of package '...',
        but prior to execution of '<module>'; this may result in
        unpredictable behaviour

    This helper temporarily removes the module from sys.modules to suppress
    the warning, then restores it so subsequent tests in the same worker
    still see the original (monkeypatched) module object.
    """
    saved = sys.modules.pop(module_name, None)
    try:
        runpy.run_module(module_name, run_name="__main__")
    finally:
        if saved is not None:
            sys.modules[module_name] = saved
