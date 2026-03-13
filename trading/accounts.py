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
) -> None:
    if initial_cash <= 0:
        raise ValueError("initial_cash must be greater than 0.")
    conn.execute(
        """
        INSERT INTO accounts (name, strategy, initial_cash, created_at, benchmark_ticker)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, strategy, float(initial_cash), utc_now_iso(), benchmark_ticker.upper().strip()),
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
        SELECT id, name, strategy, initial_cash, created_at, benchmark_ticker
        FROM accounts
        ORDER BY id
        """
    ).fetchall()
    if not rows:
        print("No paper accounts found.")
        return

    for row in rows:
        print(
            f"[{row['id']}] {row['name']} | strategy={row['strategy']} | "
            f"initial_cash={row['initial_cash']:.2f} | benchmark={row['benchmark_ticker']} | "
            f"created={row['created_at']}"
        )
