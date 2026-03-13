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

        risk_policy = profile.get("risk_policy")
        if risk_policy is not None:
            risk_policy = str(risk_policy)

        stop_loss_pct = profile.get("stop_loss_pct")
        take_profit_pct = profile.get("take_profit_pct")

        instrument_mode = profile.get("instrument_mode")
        if instrument_mode is not None:
            instrument_mode = str(instrument_mode)

        option_strike_offset_pct = profile.get("option_strike_offset_pct")
        option_min_dte = profile.get("option_min_dte")
        option_max_dte = profile.get("option_max_dte")
        option_type = profile.get("option_type")
        if option_type is not None:
            option_type = str(option_type)
        target_delta_min = profile.get("target_delta_min")
        target_delta_max = profile.get("target_delta_max")
        max_premium_per_trade = profile.get("max_premium_per_trade")
        max_contracts_per_trade = profile.get("max_contracts_per_trade")
        iv_rank_min = profile.get("iv_rank_min")
        iv_rank_max = profile.get("iv_rank_max")
        roll_dte_threshold = profile.get("roll_dte_threshold")
        profit_take_pct = profile.get("profit_take_pct")
        max_loss_pct = profile.get("max_loss_pct")

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
                risk_policy=risk_policy or "none",
                stop_loss_pct=float(stop_loss_pct) if stop_loss_pct is not None else None,
                take_profit_pct=float(take_profit_pct) if take_profit_pct is not None else None,
                instrument_mode=instrument_mode or "equity",
                option_strike_offset_pct=(
                    float(option_strike_offset_pct)
                    if option_strike_offset_pct is not None
                    else None
                ),
                option_min_dte=int(option_min_dte) if option_min_dte is not None else None,
                option_max_dte=int(option_max_dte) if option_max_dte is not None else None,
                option_type=option_type,
                target_delta_min=float(target_delta_min) if target_delta_min is not None else None,
                target_delta_max=float(target_delta_max) if target_delta_max is not None else None,
                max_premium_per_trade=(
                    float(max_premium_per_trade)
                    if max_premium_per_trade is not None
                    else None
                ),
                max_contracts_per_trade=(
                    int(max_contracts_per_trade)
                    if max_contracts_per_trade is not None
                    else None
                ),
                iv_rank_min=float(iv_rank_min) if iv_rank_min is not None else None,
                iv_rank_max=float(iv_rank_max) if iv_rank_max is not None else None,
                roll_dte_threshold=(
                    int(roll_dte_threshold)
                    if roll_dte_threshold is not None
                    else None
                ),
                profit_take_pct=float(profit_take_pct) if profit_take_pct is not None else None,
                max_loss_pct=float(max_loss_pct) if max_loss_pct is not None else None,
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
                "risk_policy",
                "stop_loss_pct",
                "take_profit_pct",
                "instrument_mode",
                "option_strike_offset_pct",
                "option_min_dte",
                "option_max_dte",
                "option_type",
                "target_delta_min",
                "target_delta_max",
                "max_premium_per_trade",
                "max_contracts_per_trade",
                "iv_rank_min",
                "iv_rank_max",
                "roll_dte_threshold",
                "profit_take_pct",
                "max_loss_pct",
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
                risk_policy=risk_policy,
                stop_loss_pct=float(stop_loss_pct) if stop_loss_pct is not None else None,
                take_profit_pct=float(take_profit_pct) if take_profit_pct is not None else None,
                instrument_mode=instrument_mode,
                option_strike_offset_pct=(
                    float(option_strike_offset_pct)
                    if option_strike_offset_pct is not None
                    else None
                ),
                option_min_dte=int(option_min_dte) if option_min_dte is not None else None,
                option_max_dte=int(option_max_dte) if option_max_dte is not None else None,
                option_type=option_type,
                target_delta_min=float(target_delta_min) if target_delta_min is not None else None,
                target_delta_max=float(target_delta_max) if target_delta_max is not None else None,
                max_premium_per_trade=(
                    float(max_premium_per_trade)
                    if max_premium_per_trade is not None
                    else None
                ),
                max_contracts_per_trade=(
                    int(max_contracts_per_trade)
                    if max_contracts_per_trade is not None
                    else None
                ),
                iv_rank_min=float(iv_rank_min) if iv_rank_min is not None else None,
                iv_rank_max=float(iv_rank_max) if iv_rank_max is not None else None,
                roll_dte_threshold=(
                    int(roll_dte_threshold)
                    if roll_dte_threshold is not None
                    else None
                ),
                profit_take_pct=float(profit_take_pct) if profit_take_pct is not None else None,
                max_loss_pct=float(max_loss_pct) if max_loss_pct is not None else None,
            )
            fields_updated = True

        if fields_updated:
            updated += 1
        else:
            skipped += 1

    return created, updated, skipped
