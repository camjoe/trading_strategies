import sqlite3
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_account(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise ValueError(f"Account '{name}' not found.")
    return row


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
) -> None:
    if initial_cash <= 0:
        raise ValueError("initial_cash must be greater than 0.")
    if goal_min_return_pct is not None and goal_max_return_pct is not None:
        if goal_min_return_pct > goal_max_return_pct:
            raise ValueError("goal_min_return_pct cannot be greater than goal_max_return_pct.")

    display = (descriptive_name or name).strip()
    if not display:
        display = name

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
            learning_enabled
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
               goal_min_return_pct, goal_max_return_pct, goal_period, learning_enabled
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

    min_value = goal_min_return_pct
    max_value = goal_max_return_pct
    if min_value is None:
        min_value = account["goal_min_return_pct"]
    if max_value is None:
        max_value = account["goal_max_return_pct"]
    if min_value is not None and max_value is not None and float(min_value) > float(max_value):
        raise ValueError("goal_min_return_pct cannot be greater than goal_max_return_pct.")

    if not updates:
        return

    params.append(account["id"])
    conn.execute(f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?", tuple(params))
    conn.commit()
