from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from common.project_paths import (
    EXPORTS_DIR as DEFAULT_EXPORTS_DIR,
    LEGACY_TEST_INVESTMENTS_PATH,
    LOGS_DIR as PROJECT_LOGS_DIR,
    REPO_ROOT,
    TEST_INVESTMENTS_PATH,
)

DEFAULT_CORS_ORIGIN = "*"
DEFAULT_LOGS_DIR_RELATIVE = "local/logs"
ROOT_DIR = REPO_ROOT
BACKEND_DIR = Path(__file__).resolve().parent

load_dotenv(BACKEND_DIR / ".env")


def _parse_cors_origins(raw: str) -> list[str]:
    cleaned = [item.strip() for item in raw.split(",") if item.strip()]
    return cleaned or [DEFAULT_CORS_ORIGIN]


logs_dir_raw = os.getenv("LOGS_DIR")
LOGS_DIR = (
    PROJECT_LOGS_DIR
    if not logs_dir_raw
    else (
        (ROOT_DIR / logs_dir_raw).resolve()
        if not Path(logs_dir_raw).is_absolute()
        else Path(logs_dir_raw).resolve()
    )
)
EXPORTS_DIR = DEFAULT_EXPORTS_DIR
TEST_INVESTMENTS_CANDIDATES = (
    TEST_INVESTMENTS_PATH,
    LEGACY_TEST_INVESTMENTS_PATH,  # legacy typo fallback
)
TEST_ACCOUNT_NAME = "test_account"
TEST_BACKTEST_ACCOUNT_NAME = "test_account_bt"
TEST_ACCOUNT_DISPLAY_NAME = "TEST Account"
TEST_ACCOUNT_STRATEGY = "Manual Test Investments"
TEST_ACCOUNT_BENCHMARK_DEFAULT = "SPY"
TEST_ACCOUNT_TRADE_TIME = "2025-01-11T12:00:00Z"
CORS_ORIGINS = _parse_cors_origins(os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGIN))
