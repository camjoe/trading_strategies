#!/usr/bin/env python3
"""Restore the disposable sandbox database and launch the UI against it.

The sandbox is a test bed, not a demo: it carries two years of history across
several accounts and books so feature work and code checks run against a
database that resembles a used one.

Nothing written to it survives. Each run restores a fresh working copy from the
cached golden build, so the bed is byte-identical every launch and experiments
cannot accumulate. Pass ``--rebuild`` to regenerate the golden itself (it is
also rebuilt automatically when the schema head or the seeder source changes).

Usage:
    python -m scripts.launch_sandbox            # restore and launch the UI
    python -m scripts.launch_sandbox --rebuild  # regenerate the golden first
    python -m scripts.launch_sandbox --no-ui    # restore only, print the path
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from scripts import launch_ui
from scripts.fixture_db import checkout_sandbox
from scripts.ui_config import SANDBOX_BACKEND_PORT, SANDBOX_FRONTEND_PORT
from trading.services.fixtures.profiles import SANDBOX_PROFILE

SANDBOX_DATABASE_NAME = "sandbox.db"
GOLDEN_DATABASE_NAME = "sandbox.golden.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore the disposable sandbox database and launch the UI.")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Regenerate the golden build before restoring the working copy.",
    )
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Restore the database and print its path without starting the UI.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    # Only the UI path needs the frontend toolchain; --no-ui restores the database
    # for CLI and test use, which npm has nothing to do with.
    if not args.no_ui:
        preflight_error = launch_ui.preflight(repo_root)
        if preflight_error:
            print(f"Error: {preflight_error}", file=sys.stderr)
            return 1
    try:
        database_path, rebuilt = checkout_sandbox(
            repo_root,
            profile=SANDBOX_PROFILE,
            golden_name=GOLDEN_DATABASE_NAME,
            working_name=SANDBOX_DATABASE_NAME,
            force_rebuild=args.rebuild,
        )
    except Exception as exc:
        print(f"Error: could not restore the sandbox database: {exc}", file=sys.stderr)
        return 1

    if rebuilt:
        print(f"Rebuilt golden sandbox build: {repo_root / 'local' / GOLDEN_DATABASE_NAME}")
    print(f"Restored disposable sandbox database: {database_path}")

    os.environ.update(
        {
            "TRADING_DB_PATH": str(database_path),
            "TRADING_MARKET_DATA_PROVIDER": "demo",
            "TRADING_EXTERNAL_FEATURES_DISABLED": "1",
        }
    )
    if args.no_ui:
        print("Point tooling at it with: TRADING_DB_PATH=" + str(database_path))
        return 0
    return launch_ui.main(backend_port=SANDBOX_BACKEND_PORT, frontend_port=SANDBOX_FRONTEND_PORT)


if __name__ == "__main__":
    raise SystemExit(main())
