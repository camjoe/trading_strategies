#!/usr/bin/env python3
"""Prepare and launch the fully offline seeded paper-trading demo."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sqlite3
import sys
from pathlib import Path

from infrastructure.database.migration_runner import upgrade
from scripts import launch_ui
from scripts.ui_config import DEMO_BACKEND_PORT, DEMO_FRONTEND_PORT
from trading.services.demo import seed_demo_database

DEMO_DATABASE_NAME = "demo.db"
PREPARING_DATABASE_NAME = "demo.preparing.db"
SQLITE_SIDECAR_SUFFIXES = ("", "-shm", "-wal", "-journal")


def _exact_demo_targets(local_dir: Path, database_name: str) -> tuple[Path, ...]:
    """Return only the named SQLite file and its recognized sidecars under local/."""
    resolved_local = local_dir.resolve()
    database = (resolved_local / database_name).resolve()
    if database.parent != resolved_local or database.name != database_name:
        raise ValueError("Demo database target must be an exact filename directly under local/.")
    return tuple(Path(f"{database}{suffix}") for suffix in SQLITE_SIDECAR_SUFFIXES)


def _remove_exact_targets(local_dir: Path, database_name: str) -> None:
    for target in _exact_demo_targets(local_dir, database_name):
        target.unlink(missing_ok=True)


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
    local_dir = (repo_root / "local").resolve()
    local_dir.mkdir(parents=True, exist_ok=True)
    final_path = _exact_demo_targets(local_dir, DEMO_DATABASE_NAME)[0]
    preparing_path = _exact_demo_targets(local_dir, PREPARING_DATABASE_NAME)[0]
    _remove_exact_targets(local_dir, PREPARING_DATABASE_NAME)
    try:
        conn = sqlite3.connect(preparing_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            upgrade(connection=conn)
            seed_demo_database(conn)
        finally:
            conn.close()
        _remove_exact_targets(local_dir, DEMO_DATABASE_NAME)
        os.replace(preparing_path, final_path)
    except BaseException:
        _remove_exact_targets(local_dir, PREPARING_DATABASE_NAME)
        raise
    return final_path


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
