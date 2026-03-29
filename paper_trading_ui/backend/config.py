from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from common.repo_paths import get_repo_root

ROOT_DIR = get_repo_root(__file__)
BACKEND_DIR = Path(__file__).resolve().parent

load_dotenv(BACKEND_DIR / ".env")


def _parse_cors_origins(raw: str) -> list[str]:
    cleaned = [item.strip() for item in raw.split(",") if item.strip()]
    return cleaned or ["*"]


logs_dir_raw = os.getenv("LOGS_DIR", "local/logs")
LOGS_DIR = (ROOT_DIR / logs_dir_raw).resolve() if not Path(logs_dir_raw).is_absolute() else Path(logs_dir_raw).resolve()
EXPORTS_DIR = (ROOT_DIR / "local" / "exports").resolve()
TEST_INVESTMENTS_CANDIDATES = (
    (ROOT_DIR / "local" / "test_investments.txt").resolve(),
    (ROOT_DIR / "local" / "test_invesments.txt").resolve(),
)
TEST_ACCOUNT_NAME = "test_account"
TEST_BACKTEST_ACCOUNT_NAME = "test_account_bt"
TEST_ACCOUNT_DISPLAY_NAME = "TEST Account"
TEST_ACCOUNT_STRATEGY = "Manual Test Investments"
TEST_ACCOUNT_BENCHMARK_DEFAULT = "SPY"
TEST_ACCOUNT_TRADE_TIME = "2025-01-11T12:00:00Z"
CORS_ORIGINS = _parse_cors_origins(os.getenv("CORS_ORIGINS", "*"))
