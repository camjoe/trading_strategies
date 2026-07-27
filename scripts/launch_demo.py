#!/usr/bin/env python3
"""Prepare and launch the fully offline seeded paper-trading demo."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

from scripts import launch_ui
from scripts.fixture_db import build_fixture_database
from scripts.ui_config import DEMO_BACKEND_PORT, DEMO_FRONTEND_PORT
from trading.services.fixtures import DEMO_PROFILE

DEMO_DATABASE_NAME = "demo.db"
PREPARING_DATABASE_NAME = "demo.preparing.db"


def _preflight(repo_root: Path) -> str | None:
    npm = launch_ui.npm_command()
    if shutil.which(npm) is None:
        return (
            "npm was not found in PATH. Install Node.js 24, then run: npm ci --prefix apps/paper_trading_web/frontend"
        )
    frontend_dir = repo_root / "apps" / "paper_trading_web" / "frontend"
    if not (frontend_dir / "node_modules").is_dir():
        return "Frontend dependencies are missing. Run: npm ci --prefix apps/paper_trading_web/frontend"
    missing = [
        name for name in ("alembic", "pandas", "sqlalchemy", "uvicorn") if importlib.util.find_spec(name) is None
    ]
    if missing:
        return f"Python dependencies are missing ({', '.join(missing)}). Run: {sys.executable} -m pip install -r requirements-dev.txt"
    return None


def prepare_demo_database(repo_root: Path) -> Path:
    """Migrate and seed a temporary DB, publishing it only after success."""
    return build_fixture_database(
        repo_root,
        profile=DEMO_PROFILE,
        database_name=DEMO_DATABASE_NAME,
        preparing_name=PREPARING_DATABASE_NAME,
    )


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    preflight_error = _preflight(repo_root)
    if preflight_error:
        print(f"Error: {preflight_error}", file=sys.stderr)
        return 1
    try:
        database_path = prepare_demo_database(repo_root)
    except Exception as exc:
        print(f"Error: could not prepare demo database: {exc}", file=sys.stderr)
        return 1

    os.environ.update(
        {
            "TRADING_DB_PATH": str(database_path),
            "TRADING_MARKET_DATA_PROVIDER": "demo",
            "TRADING_EXTERNAL_FEATURES_DISABLED": "1",
            "VITE_DEMO_MODE": "1",
        }
    )
    print(f"Prepared fresh offline demo database: {database_path}")
    return launch_ui.main(backend_port=DEMO_BACKEND_PORT, frontend_port=DEMO_FRONTEND_PORT)


if __name__ == "__main__":
    raise SystemExit(main())
