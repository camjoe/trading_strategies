import json
import sqlite3
from pathlib import Path

try:
    from trading.accounts import configure_account, create_account, get_account, set_benchmark
except ModuleNotFoundError:
    from accounts import configure_account, create_account, get_account, set_benchmark


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "on"}:
            return True
        if v in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"Invalid boolean value: {value}")


def load_account_profiles(file_path: str) -> list[dict[str, object]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Profile file not found: {file_path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(raw, dict):
        profiles = raw.get("accounts", [])
    else:
        profiles = raw

    if not isinstance(profiles, list):
        raise ValueError("Profile file must be a list or an object with an 'accounts' list.")

    out: list[dict[str, object]] = []
    for i, item in enumerate(profiles, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Account profile at index {i} is not an object.")
        if "name" not in item or not str(item["name"]).strip():
            raise ValueError(f"Account profile at index {i} is missing required 'name'.")
        out.append(item)

    return out


def apply_account_profiles(
    conn: sqlite3.Connection,
    profiles: list[dict[str, object]],
    create_missing: bool,
) -> tuple[int, int, int]:
    created = 0
    updated = 0
    skipped = 0

    for profile in profiles:
        name = str(profile["name"]).strip()

        try:
            get_account(conn, name)
            exists = True
        except ValueError:
            exists = False

        benchmark = str(profile.get("benchmark_ticker", "SPY")).strip().upper()
        strategy = str(profile.get("strategy", "Unspecified")).strip()
        initial_cash = float(profile.get("initial_cash", 5000.0))

        descriptive_name = profile.get("descriptive_name")
        if descriptive_name is not None:
            descriptive_name = str(descriptive_name)

        goal_min = profile.get("goal_min_return_pct")
        goal_max = profile.get("goal_max_return_pct")
        goal_period = profile.get("goal_period")
        if goal_period is not None:
            goal_period = str(goal_period)

        learning_enabled = profile.get("learning_enabled")
        if learning_enabled is not None:
            learning_enabled = _to_bool(learning_enabled)

        if not exists:
            if not create_missing:
                skipped += 1
                continue

            create_account(
                conn,
                name=name,
                strategy=strategy,
                initial_cash=initial_cash,
                benchmark_ticker=benchmark,
                descriptive_name=descriptive_name,
                goal_min_return_pct=float(goal_min) if goal_min is not None else None,
                goal_max_return_pct=float(goal_max) if goal_max is not None else None,
                goal_period=goal_period or "monthly",
                learning_enabled=bool(learning_enabled) if learning_enabled is not None else False,
            )
            created += 1
            continue

        fields_updated = False

        if "benchmark_ticker" in profile:
            set_benchmark(conn, name, benchmark)
            fields_updated = True

        if "strategy" in profile and strategy:
            account = get_account(conn, name)
            conn.execute("UPDATE accounts SET strategy = ? WHERE id = ?", (strategy, account["id"]))
            conn.commit()
            fields_updated = True

        if any(
            key in profile
            for key in [
                "descriptive_name",
                "goal_min_return_pct",
                "goal_max_return_pct",
                "goal_period",
                "learning_enabled",
            ]
        ):
            configure_account(
                conn,
                account_name=name,
                descriptive_name=descriptive_name,
                goal_min_return_pct=float(goal_min) if goal_min is not None else None,
                goal_max_return_pct=float(goal_max) if goal_max is not None else None,
                goal_period=goal_period,
                learning_enabled=learning_enabled,
            )
            fields_updated = True

        if fields_updated:
            updated += 1
        else:
            skipped += 1

    return created, updated, skipped
