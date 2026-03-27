#!/usr/bin/env python3
"""Run the daily paper-trading workflow with log + duplicate-run guard."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import subprocess
import sys
import traceback
from pathlib import Path

from common.repo_paths import get_repo_root

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = REPO_ROOT / "local" / "logs"
DEFAULT_TRADE_CAPS_CONFIG = "trading/scripts/account_trade_caps.json"


def _startup_log(message: str) -> None:
    log_path = LOGS_DIR / f"daily_paper_trading_startup_{dt.date.today().strftime('%Y%m%d')}.log"
    timestamp = dt.datetime.now(dt.timezone.utc).astimezone().isoformat()
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


_startup_log(f"BOOT: script={__file__} cwd={Path.cwd()} python={sys.executable}")

try:
    from trading.database.db_config import get_db_path
except Exception as exc:
    _startup_log(f"IMPORT ERROR: {exc}")
    _startup_log(traceback.format_exc().rstrip())
    raise


COMPLETE_SENTINEL = "COMPLETE: Daily paper trading run succeeded."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the daily paper-trading workflow.")
    parser.add_argument(
        "--accounts",
        default="all",
        help="Comma-separated account names, or 'all' for every account in DB (default: all)",
    )
    parser.add_argument(
        "--primary-accounts",
        default="momentum_5k,meanrev_5k",
        help="Accounts that keep strict legacy limits (default: momentum_5k,meanrev_5k)",
    )
    parser.add_argument("--primary-min-trades", type=int, default=1)
    parser.add_argument("--primary-max-trades", type=int, default=5)
    parser.add_argument("--other-min-trades", type=int, default=1)
    parser.add_argument("--other-max-trades", type=int, default=11)
    parser.add_argument(
        "--account-trade-caps",
        default="",
        help=(
            "Optional per-account overrides in the form "
            "account:min-max,account:min-max (example: momentum_5k:1-5,core_growth_20k:1-8)"
        ),
    )
    parser.add_argument(
        "--trade-caps-config",
        default=DEFAULT_TRADE_CAPS_CONFIG,
        help=(
            "Path to JSON file with default and per-account trade caps "
            f"(default: {DEFAULT_TRADE_CAPS_CONFIG})"
        ),
    )
    parser.add_argument("--fee", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--force-run", action="store_true", help="Allow duplicate same-day run")
    parser.add_argument("--run-source", default="scheduled-daily")
    return parser.parse_args()


def load_all_account_names() -> list[str]:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT name FROM accounts ORDER BY name ASC").fetchall()
    finally:
        conn.close()
    return [str(row["name"]) for row in rows]


def parse_account_trade_caps(value: str) -> dict[str, tuple[int, int]]:
    if not value.strip():
        return {}

    caps: dict[str, tuple[int, int]] = {}
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if ":" not in item or "-" not in item:
            raise ValueError(
                "--account-trade-caps entries must look like account:min-max"
            )
        account_name, raw_range = item.split(":", 1)
        min_text, max_text = raw_range.split("-", 1)
        min_trades = int(min_text)
        max_trades = int(max_text)
        if min_trades < 1:
            raise ValueError(f"{account_name}: min trades must be >= 1")
        if max_trades < min_trades:
            raise ValueError(f"{account_name}: max trades must be >= min trades")
        caps[account_name.strip()] = (min_trades, max_trades)
    return caps


def _validate_trade_cap_range(name: str, min_trades: int, max_trades: int) -> tuple[int, int]:
    if min_trades < 1:
        raise ValueError(f"{name}: min trades must be >= 1")
    if max_trades < min_trades:
        raise ValueError(f"{name}: max trades must be >= min trades")
    return min_trades, max_trades


def load_trade_caps_config(config_path: Path) -> tuple[tuple[int, int] | None, dict[str, tuple[int, int]]]:
    if not config_path.exists():
        return None, {}

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Trade caps config must be a JSON object")

    default_caps: tuple[int, int] | None = None
    raw_default = raw.get("default")
    if raw_default is not None:
        if not isinstance(raw_default, dict) or "min" not in raw_default or "max" not in raw_default:
            raise ValueError("Trade caps config 'default' must contain min and max")
        default_caps = _validate_trade_cap_range(
            "default",
            int(raw_default["min"]),
            int(raw_default["max"]),
        )

    account_caps: dict[str, tuple[int, int]] = {}
    raw_accounts = raw.get("accounts", {})
    if not isinstance(raw_accounts, dict):
        raise ValueError("Trade caps config 'accounts' must be an object")

    for account_name, caps in raw_accounts.items():
        if not isinstance(caps, dict) or "min" not in caps or "max" not in caps:
            raise ValueError(f"Trade caps config for account '{account_name}' must contain min and max")
        account_caps[account_name] = _validate_trade_cap_range(
            account_name,
            int(caps["min"]),
            int(caps["max"]),
        )

    return default_caps, account_caps


def resolve_trade_caps(
    accounts: list[str],
    configured_default_caps: tuple[int, int] | None,
    configured_account_caps: dict[str, tuple[int, int]],
    primary_accounts: set[str],
    primary_min_trades: int,
    primary_max_trades: int,
    other_min_trades: int,
    other_max_trades: int,
    account_trade_cap_overrides: dict[str, tuple[int, int]],
) -> dict[str, tuple[int, int]]:
    resolved: dict[str, tuple[int, int]] = {}
    for account in accounts:
        if account in account_trade_cap_overrides:
            resolved[account] = account_trade_cap_overrides[account]
            continue
        if account in configured_account_caps:
            resolved[account] = configured_account_caps[account]
            continue
        if configured_default_caps is not None:
            resolved[account] = configured_default_caps
            continue
        if account in primary_accounts:
            resolved[account] = (primary_min_trades, primary_max_trades)
        else:
            resolved[account] = (other_min_trades, other_max_trades)
    return resolved


def tee_line(log_path: Path, text: str) -> None:
    print(text)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def stream_command(log_path: Path, label: str, args: list[str], cwd: Path) -> None:
    tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] START: {label}")
    process = subprocess.Popen(
        [sys.executable, *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    assert process.stdout is not None
    for line in process.stdout:
        tee_line(log_path, line.rstrip("\n"))
    exit_code = process.wait()
    if exit_code != 0:
        raise RuntimeError(f"Step failed: {label} (exit={exit_code})")
    tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] DONE: {label}")


def already_completed_today(log_dir: Path) -> bool:
    today_tag = dt.date.today().strftime("%Y%m%d")
    logs = sorted(log_dir.glob(f"daily_paper_trading_{today_tag}_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        return False
    latest = logs[0]
    try:
        return COMPLETE_SENTINEL in latest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def main() -> int:
    _startup_log("main() entered")
    args = parse_args()

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    if not args.force_run and already_completed_today(LOGS_DIR):
        _startup_log(f"SKIP duplicate run (source={args.run_source})")
        print(f"Daily paper trading already completed today; skipping duplicate run. source={args.run_source}")
        return 0

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"daily_paper_trading_{timestamp}.log"
    _startup_log(f"RUN log_path={log_path}")

    all_accounts = load_all_account_names()

    if args.accounts.strip().lower() == "all":
        accounts = all_accounts
    else:
        requested = [item.strip() for item in args.accounts.split(",") if item.strip()]
        known = set(all_accounts)
        missing = [name for name in requested if name not in known]
        if missing:
            print(f"Unknown account(s): {', '.join(missing)}", file=sys.stderr)
            return 1
        accounts = requested

    if not accounts:
        print("No accounts specified.", file=sys.stderr)
        return 1

    if args.primary_min_trades < 1:
        print("--primary-min-trades must be >= 1", file=sys.stderr)
        return 1
    if args.primary_max_trades < args.primary_min_trades:
        print("--primary-max-trades must be >= --primary-min-trades", file=sys.stderr)
        return 1
    if args.other_min_trades < 1:
        print("--other-min-trades must be >= 1", file=sys.stderr)
        return 1
    if args.other_max_trades < args.other_min_trades:
        print("--other-max-trades must be >= --other-min-trades", file=sys.stderr)
        return 1

    primary_accounts = {item.strip() for item in args.primary_accounts.split(",") if item.strip()}
    caps_config_path = Path(args.trade_caps_config)
    if not caps_config_path.is_absolute():
        caps_config_path = REPO_ROOT / caps_config_path

    try:
        configured_default_caps, configured_account_caps = load_trade_caps_config(caps_config_path)
    except ValueError as exc:
        print(f"Invalid trade caps config: {exc}", file=sys.stderr)
        return 1

    try:
        account_trade_cap_overrides = parse_account_trade_caps(args.account_trade_caps)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    unknown_override_accounts = [name for name in account_trade_cap_overrides if name not in set(all_accounts)]
    if unknown_override_accounts:
        print(
            f"Unknown account(s) in --account-trade-caps: {', '.join(unknown_override_accounts)}",
            file=sys.stderr,
        )
        return 1

    account_trade_caps = resolve_trade_caps(
        accounts,
        configured_default_caps,
        configured_account_caps,
        primary_accounts,
        args.primary_min_trades,
        args.primary_max_trades,
        args.other_min_trades,
        args.other_max_trades,
        account_trade_cap_overrides,
    )
    caps_summary = ",".join(
        f"{name}:{limits[0]}-{limits[1]}" for name, limits in account_trade_caps.items()
    )

    tee_line(
        log_path,
        f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] RUN META: "
        f"source={args.run_source} force={bool(args.force_run)} "
        f"accounts={','.join(accounts)} caps={caps_summary}",
    )

    try:
        def _run_auto_trader_group(label: str, group_accounts: list[str], min_trades: int, max_trades: int) -> None:
            if not group_accounts:
                return
            auto_trader_args = [
                "-m",
                "trading.auto_trader",
                "--accounts",
                ",".join(group_accounts),
                "--min-trades",
                str(min_trades),
                "--max-trades",
                str(max_trades),
                "--fee",
                str(args.fee),
            ]
            if args.seed is not None:
                auto_trader_args.extend(["--seed", str(args.seed)])
            stream_command(log_path, label, auto_trader_args, REPO_ROOT)

        grouped_accounts: dict[tuple[int, int], list[str]] = {}
        for account_name in accounts:
            limits = account_trade_caps[account_name]
            grouped_accounts.setdefault(limits, []).append(account_name)

        for limits, group_accounts in sorted(grouped_accounts.items(), key=lambda item: (item[0][0], item[0][1], item[1])):
            min_trades, max_trades = limits
            _run_auto_trader_group(
                f"Auto Trader ({min_trades}-{max_trades} trades)",
                group_accounts,
                min_trades,
                max_trades,
            )

        for account in accounts:
            stream_command(
                log_path,
                f"Snapshot {account}",
                ["-m", "trading.paper_trading", "snapshot", "--account", account],
                REPO_ROOT,
            )

        stream_command(
            log_path,
            "Compare Strategies",
            ["-m", "trading.paper_trading", "compare-strategies", "--lookback", "10"],
            REPO_ROOT,
        )

        tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] {COMPLETE_SENTINEL}")
        return 0
    except Exception as exc:
        tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
