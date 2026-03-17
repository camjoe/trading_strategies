import json
import sqlite3
from pathlib import Path

try:
    from trading.accounts import configure_account, create_account, get_account, set_benchmark
    from trading.db_coercion import coerce_bool, coerce_float, coerce_int
except ModuleNotFoundError:
    from accounts import configure_account, create_account, get_account, set_benchmark
    from db_coercion import coerce_bool, coerce_float, coerce_int


_CONFIGURE_KEYS = {
    "descriptive_name", "goal_min_return_pct", "goal_max_return_pct", "goal_period",
    "learning_enabled", "risk_policy", "stop_loss_pct", "take_profit_pct",
    "instrument_mode", "option_strike_offset_pct", "option_min_dte", "option_max_dte",
    "option_type", "target_delta_min", "target_delta_max", "max_premium_per_trade",
    "max_contracts_per_trade", "iv_rank_min", "iv_rank_max", "roll_dte_threshold",
    "profit_take_pct", "max_loss_pct",
}

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


def _extract_profile_fields(profile: dict[str, object]) -> dict[str, object]:
    """Normalize and type-coerce all configurable fields from a raw profile dict."""
    g = profile.get
    learning = g("learning_enabled")
    return {
        "descriptive_name": str(g("descriptive_name")) if g("descriptive_name") is not None else None,
        "goal_min_return_pct": coerce_float(g("goal_min_return_pct")),
        "goal_max_return_pct": coerce_float(g("goal_max_return_pct")),
        "goal_period": str(g("goal_period")) if g("goal_period") is not None else None,
        "learning_enabled": coerce_bool(learning) if learning is not None else None,
        "risk_policy": str(g("risk_policy")) if g("risk_policy") is not None else None,
        "stop_loss_pct": coerce_float(g("stop_loss_pct")),
        "take_profit_pct": coerce_float(g("take_profit_pct")),
        "instrument_mode": str(g("instrument_mode")) if g("instrument_mode") is not None else None,
        "option_strike_offset_pct": coerce_float(g("option_strike_offset_pct")),
        "option_min_dte": coerce_int(g("option_min_dte")),
        "option_max_dte": coerce_int(g("option_max_dte")),
        "option_type": str(g("option_type")) if g("option_type") is not None else None,
        "target_delta_min": coerce_float(g("target_delta_min")),
        "target_delta_max": coerce_float(g("target_delta_max")),
        "max_premium_per_trade": coerce_float(g("max_premium_per_trade")),
        "max_contracts_per_trade": coerce_int(g("max_contracts_per_trade")),
        "iv_rank_min": coerce_float(g("iv_rank_min")),
        "iv_rank_max": coerce_float(g("iv_rank_max")),
        "roll_dte_threshold": coerce_int(g("roll_dte_threshold")),
        "profit_take_pct": coerce_float(g("profit_take_pct")),
        "max_loss_pct": coerce_float(g("max_loss_pct")),
    }


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
        benchmark = str(profile.get("benchmark_ticker", "SPY")).strip().upper()
        strategy = str(profile.get("strategy", "Unspecified")).strip()
        initial_cash = coerce_float(profile.get("initial_cash", 5000.0))
        if initial_cash is None:
            raise ValueError("initial_cash cannot be null")

        try:
            get_account(conn, name)
            exists = True
        except ValueError:
            exists = False

        if not exists:
            if not create_missing:
                skipped += 1
                continue

            fields = _extract_profile_fields(profile)
            create_kwargs = {**fields}
            create_kwargs["goal_period"] = fields["goal_period"] or "monthly"
            create_kwargs["learning_enabled"] = fields["learning_enabled"] if fields["learning_enabled"] is not None else False
            create_kwargs["risk_policy"] = fields["risk_policy"] or "none"
            create_kwargs["instrument_mode"] = fields["instrument_mode"] or "equity"
            create_account(conn, name=name, strategy=strategy, initial_cash=initial_cash, benchmark_ticker=benchmark, **create_kwargs)
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

        if any(key in profile for key in _CONFIGURE_KEYS):
            fields = _extract_profile_fields(profile)
            configure_account(conn, account_name=name, **fields)
            fields_updated = True

        if fields_updated:
            updated += 1
        else:
            skipped += 1

    return created, updated, skipped
