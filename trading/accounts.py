import sqlite3
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_account(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise ValueError(f"Account '{name}' not found.")
    return row


def _validate_option_settings(
    option_type: str | None,
    target_delta_min: float | None,
    target_delta_max: float | None,
    option_min_dte: int | None,
    option_max_dte: int | None,
    iv_rank_min: float | None,
    iv_rank_max: float | None,
) -> None:
    if option_type is not None and option_type not in {"call", "put", "both"}:
        raise ValueError("option_type must be one of: call, put, both")
    if target_delta_min is not None and not (0 <= float(target_delta_min) <= 1):
        raise ValueError("target_delta_min must be between 0 and 1.")
    if target_delta_max is not None and not (0 <= float(target_delta_max) <= 1):
        raise ValueError("target_delta_max must be between 0 and 1.")
    if (
        target_delta_min is not None
        and target_delta_max is not None
        and float(target_delta_min) > float(target_delta_max)
    ):
        raise ValueError("target_delta_min cannot be greater than target_delta_max.")
    if option_min_dte is not None and int(option_min_dte) < 0:
        raise ValueError("option_min_dte must be >= 0.")
    if option_max_dte is not None and int(option_max_dte) < 0:
        raise ValueError("option_max_dte must be >= 0.")
    if option_min_dte is not None and option_max_dte is not None and int(option_min_dte) > int(option_max_dte):
        raise ValueError("option_min_dte cannot be greater than option_max_dte.")
    if iv_rank_min is not None and not (0 <= float(iv_rank_min) <= 100):
        raise ValueError("iv_rank_min must be between 0 and 100.")
    if iv_rank_max is not None and not (0 <= float(iv_rank_max) <= 100):
        raise ValueError("iv_rank_max must be between 0 and 100.")
    if iv_rank_min is not None and iv_rank_max is not None and float(iv_rank_min) > float(iv_rank_max):
        raise ValueError("iv_rank_min cannot be greater than iv_rank_max.")


def create_account(
    conn: sqlite3.Connection,
    name: str,
    strategy: str,
    initial_cash: float,
    benchmark_ticker: str,
    descriptive_name: str | None = None,
    goal_min_return_pct: float | None = None,
    goal_max_return_pct: float | None = None,
    goal_period: str = "monthly",
    learning_enabled: bool = False,
    risk_policy: str = "none",
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    instrument_mode: str = "equity",
    option_strike_offset_pct: float | None = None,
    option_min_dte: int | None = None,
    option_max_dte: int | None = None,
    option_type: str | None = None,
    target_delta_min: float | None = None,
    target_delta_max: float | None = None,
    max_premium_per_trade: float | None = None,
    max_contracts_per_trade: int | None = None,
    iv_rank_min: float | None = None,
    iv_rank_max: float | None = None,
    roll_dte_threshold: int | None = None,
    profit_take_pct: float | None = None,
    max_loss_pct: float | None = None,
) -> None:
    if initial_cash <= 0:
        raise ValueError("initial_cash must be greater than 0.")
    if goal_min_return_pct is not None and goal_max_return_pct is not None:
        if goal_min_return_pct > goal_max_return_pct:
            raise ValueError("goal_min_return_pct cannot be greater than goal_max_return_pct.")

    display = (descriptive_name or name).strip()
    if not display:
        display = name

    risk = risk_policy.strip().lower()
    mode = instrument_mode.strip().lower()
    if risk not in {"none", "fixed_stop", "take_profit", "stop_and_target"}:
        raise ValueError("risk_policy must be one of: none, fixed_stop, take_profit, stop_and_target")
    if mode not in {"equity", "leaps"}:
        raise ValueError("instrument_mode must be one of: equity, leaps")
    if option_min_dte is not None and option_max_dte is not None and option_min_dte > option_max_dte:
        raise ValueError("option_min_dte cannot be greater than option_max_dte.")
    _validate_option_settings(
        option_type,
        target_delta_min,
        target_delta_max,
        option_min_dte,
        option_max_dte,
        iv_rank_min,
        iv_rank_max,
    )

    conn.execute(
        """
        INSERT INTO accounts (
            name,
            strategy,
            initial_cash,
            created_at,
            benchmark_ticker,
            descriptive_name,
            goal_min_return_pct,
            goal_max_return_pct,
            goal_period,
            learning_enabled,
            risk_policy,
            stop_loss_pct,
            take_profit_pct,
            instrument_mode,
            option_strike_offset_pct,
            option_min_dte,
            option_max_dte,
            option_type,
            target_delta_min,
            target_delta_max,
            max_premium_per_trade,
            max_contracts_per_trade,
            iv_rank_min,
            iv_rank_max,
            roll_dte_threshold,
            profit_take_pct,
            max_loss_pct
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            strategy,
            float(initial_cash),
            utc_now_iso(),
            benchmark_ticker.upper().strip(),
            display,
            goal_min_return_pct,
            goal_max_return_pct,
            goal_period.strip().lower(),
            int(learning_enabled),
            risk,
            stop_loss_pct,
            take_profit_pct,
            mode,
            option_strike_offset_pct,
            option_min_dte,
            option_max_dte,
            option_type.strip().lower() if option_type else None,
            target_delta_min,
            target_delta_max,
            max_premium_per_trade,
            max_contracts_per_trade,
            iv_rank_min,
            iv_rank_max,
            roll_dte_threshold,
            profit_take_pct,
            max_loss_pct,
        ),
    )
    conn.commit()


def set_benchmark(conn: sqlite3.Connection, account_name: str, benchmark_ticker: str) -> None:
    account = get_account(conn, account_name)
    conn.execute(
        "UPDATE accounts SET benchmark_ticker = ? WHERE id = ?",
        (benchmark_ticker.upper().strip(), account["id"]),
    )
    conn.commit()


def list_accounts(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, name, descriptive_name, strategy, initial_cash, created_at, benchmark_ticker,
             goal_min_return_pct, goal_max_return_pct, goal_period, learning_enabled,
             risk_policy, stop_loss_pct, take_profit_pct, instrument_mode,
             option_strike_offset_pct, option_min_dte, option_max_dte,
             option_type, target_delta_min, target_delta_max,
             max_premium_per_trade, max_contracts_per_trade,
             iv_rank_min, iv_rank_max, roll_dte_threshold,
             profit_take_pct, max_loss_pct
        FROM accounts
        ORDER BY id
        """
    ).fetchall()
    if not rows:
        print("No paper accounts found.")
        return

    for row in rows:
        if row["goal_min_return_pct"] is None and row["goal_max_return_pct"] is None:
            goal_text = "not-set"
        elif row["goal_min_return_pct"] is not None and row["goal_max_return_pct"] is not None:
            goal_text = (
                f"{float(row['goal_min_return_pct']):.2f}% to "
                f"{float(row['goal_max_return_pct']):.2f}% per {row['goal_period']}"
            )
        elif row["goal_min_return_pct"] is not None:
            goal_text = f">= {float(row['goal_min_return_pct']):.2f}% per {row['goal_period']}"
        else:
            goal_text = f"<= {float(row['goal_max_return_pct']):.2f}% per {row['goal_period']}"

        print(
            f"[{row['id']}] {row['name']} ({row['descriptive_name']}) | strategy={row['strategy']} | "
            f"initial_cash={row['initial_cash']:.2f} | benchmark={row['benchmark_ticker']} | "
            f"goal={goal_text} | learning={'on' if int(row['learning_enabled']) else 'off'} | "
            f"risk={row['risk_policy']} | instrument={row['instrument_mode']} | "
            f"created={row['created_at']}"
        )


def configure_account(
    conn: sqlite3.Connection,
    account_name: str,
    descriptive_name: str | None = None,
    goal_min_return_pct: float | None = None,
    goal_max_return_pct: float | None = None,
    goal_period: str | None = None,
    learning_enabled: bool | None = None,
    risk_policy: str | None = None,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    instrument_mode: str | None = None,
    option_strike_offset_pct: float | None = None,
    option_min_dte: int | None = None,
    option_max_dte: int | None = None,
    option_type: str | None = None,
    target_delta_min: float | None = None,
    target_delta_max: float | None = None,
    max_premium_per_trade: float | None = None,
    max_contracts_per_trade: int | None = None,
    iv_rank_min: float | None = None,
    iv_rank_max: float | None = None,
    roll_dte_threshold: int | None = None,
    profit_take_pct: float | None = None,
    max_loss_pct: float | None = None,
) -> None:
    account = get_account(conn, account_name)
    updates: list[str] = []
    params: list[object] = []

    if descriptive_name is not None:
        display = descriptive_name.strip()
        if not display:
            raise ValueError("descriptive_name cannot be empty.")
        updates.append("descriptive_name = ?")
        params.append(display)

    if goal_period is not None:
        updates.append("goal_period = ?")
        params.append(goal_period.strip().lower())

    if goal_min_return_pct is not None:
        updates.append("goal_min_return_pct = ?")
        params.append(float(goal_min_return_pct))

    if goal_max_return_pct is not None:
        updates.append("goal_max_return_pct = ?")
        params.append(float(goal_max_return_pct))

    if learning_enabled is not None:
        updates.append("learning_enabled = ?")
        params.append(int(learning_enabled))

    if risk_policy is not None:
        risk = risk_policy.strip().lower()
        if risk not in {"none", "fixed_stop", "take_profit", "stop_and_target"}:
            raise ValueError("risk_policy must be one of: none, fixed_stop, take_profit, stop_and_target")
        updates.append("risk_policy = ?")
        params.append(risk)

    if stop_loss_pct is not None:
        updates.append("stop_loss_pct = ?")
        params.append(float(stop_loss_pct))

    if take_profit_pct is not None:
        updates.append("take_profit_pct = ?")
        params.append(float(take_profit_pct))

    if instrument_mode is not None:
        mode = instrument_mode.strip().lower()
        if mode not in {"equity", "leaps"}:
            raise ValueError("instrument_mode must be one of: equity, leaps")
        updates.append("instrument_mode = ?")
        params.append(mode)

    if option_strike_offset_pct is not None:
        updates.append("option_strike_offset_pct = ?")
        params.append(float(option_strike_offset_pct))

    if option_min_dte is not None:
        updates.append("option_min_dte = ?")
        params.append(int(option_min_dte))

    if option_max_dte is not None:
        updates.append("option_max_dte = ?")
        params.append(int(option_max_dte))

    if option_type is not None:
        opt_type = option_type.strip().lower()
        if opt_type not in {"call", "put", "both"}:
            raise ValueError("option_type must be one of: call, put, both")
        updates.append("option_type = ?")
        params.append(opt_type)

    if target_delta_min is not None:
        updates.append("target_delta_min = ?")
        params.append(float(target_delta_min))

    if target_delta_max is not None:
        updates.append("target_delta_max = ?")
        params.append(float(target_delta_max))

    if max_premium_per_trade is not None:
        updates.append("max_premium_per_trade = ?")
        params.append(float(max_premium_per_trade))

    if max_contracts_per_trade is not None:
        updates.append("max_contracts_per_trade = ?")
        params.append(int(max_contracts_per_trade))

    if iv_rank_min is not None:
        updates.append("iv_rank_min = ?")
        params.append(float(iv_rank_min))

    if iv_rank_max is not None:
        updates.append("iv_rank_max = ?")
        params.append(float(iv_rank_max))

    if roll_dte_threshold is not None:
        updates.append("roll_dte_threshold = ?")
        params.append(int(roll_dte_threshold))

    if profit_take_pct is not None:
        updates.append("profit_take_pct = ?")
        params.append(float(profit_take_pct))

    if max_loss_pct is not None:
        updates.append("max_loss_pct = ?")
        params.append(float(max_loss_pct))

    min_value = goal_min_return_pct
    max_value = goal_max_return_pct
    if min_value is None:
        min_value = account["goal_min_return_pct"]
    if max_value is None:
        max_value = account["goal_max_return_pct"]
    if min_value is not None and max_value is not None and float(min_value) > float(max_value):
        raise ValueError("goal_min_return_pct cannot be greater than goal_max_return_pct.")

    min_dte = option_min_dte if option_min_dte is not None else account["option_min_dte"]
    max_dte = option_max_dte if option_max_dte is not None else account["option_max_dte"]
    if min_dte is not None and max_dte is not None and int(min_dte) > int(max_dte):
        raise ValueError("option_min_dte cannot be greater than option_max_dte.")

    delta_min = target_delta_min if target_delta_min is not None else account["target_delta_min"]
    delta_max = target_delta_max if target_delta_max is not None else account["target_delta_max"]
    iv_min = iv_rank_min if iv_rank_min is not None else account["iv_rank_min"]
    iv_max = iv_rank_max if iv_rank_max is not None else account["iv_rank_max"]
    resolved_opt_type = option_type if option_type is not None else account["option_type"]
    _validate_option_settings(
        resolved_opt_type,
        float(delta_min) if delta_min is not None else None,
        float(delta_max) if delta_max is not None else None,
        int(min_dte) if min_dte is not None else None,
        int(max_dte) if max_dte is not None else None,
        float(iv_min) if iv_min is not None else None,
        float(iv_max) if iv_max is not None else None,
    )

    if not updates:
        return

    params.append(account["id"])
    conn.execute(f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?", tuple(params))
    conn.commit()
