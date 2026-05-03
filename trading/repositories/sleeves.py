from __future__ import annotations

import sqlite3


def insert_strategy_sleeve(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    name: str,
    status: str,
    base_ccy: str,
    start_equity: float,
    current_cash: float,
    current_equity: float,
    created_at: str,
    updated_at: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO strategy_sleeves (
            account_id,
            name,
            status,
            base_ccy,
            start_equity,
            current_cash,
            current_equity,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(account_id),
            name,
            status,
            base_ccy,
            float(start_equity),
            float(current_cash),
            float(current_equity),
            created_at,
            updated_at,
        ),
    )
    conn.commit()
    if cursor.lastrowid is None:
        raise ValueError("Expected strategy_sleeves id after insert.")
    return int(cursor.lastrowid)


def fetch_strategy_sleeve_by_id(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM strategy_sleeves
        WHERE id = ?
        """,
        (int(sleeve_id),),
    ).fetchone()


def fetch_strategy_sleeves_for_account(
    conn: sqlite3.Connection,
    *,
    account_id: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM strategy_sleeves
        WHERE account_id = ?
        ORDER BY id ASC
        """,
        (int(account_id),),
    ).fetchall()


def update_strategy_sleeve_status(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    status: str,
    updated_at: str,
) -> None:
    conn.execute(
        """
        UPDATE strategy_sleeves
        SET status = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, updated_at, int(sleeve_id)),
    )
    conn.commit()


def update_strategy_sleeve_balances(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    current_cash: float,
    current_equity: float,
    updated_at: str,
) -> None:
    conn.execute(
        """
        UPDATE strategy_sleeves
        SET current_cash = ?, current_equity = ?, updated_at = ?
        WHERE id = ?
        """,
        (float(current_cash), float(current_equity), updated_at, int(sleeve_id)),
    )
    conn.commit()


def insert_strategy_param_set(
    conn: sqlite3.Connection,
    *,
    strategy_name: str,
    version: str,
    params_json: str,
    config_version: str | None,
    is_active: int,
    created_at: str,
    updated_at: str,
    activated_at: str | None,
    deactivated_at: str | None,
    notes: str | None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO strategy_param_sets (
            strategy_name,
            version,
            params_json,
            config_version,
            is_active,
            created_at,
            updated_at,
            activated_at,
            deactivated_at,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            strategy_name,
            version,
            params_json,
            config_version,
            int(is_active),
            created_at,
            updated_at,
            activated_at,
            deactivated_at,
            notes,
        ),
    )
    conn.commit()
    if cursor.lastrowid is None:
        raise ValueError("Expected strategy_param_sets id after insert.")
    return int(cursor.lastrowid)


def fetch_strategy_param_set_by_id(
    conn: sqlite3.Connection,
    *,
    param_set_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM strategy_param_sets
        WHERE id = ?
        """,
        (int(param_set_id),),
    ).fetchone()


def fetch_active_strategy_param_set(
    conn: sqlite3.Connection,
    *,
    strategy_name: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM strategy_param_sets
        WHERE strategy_name = ? AND is_active = 1
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (strategy_name,),
    ).fetchone()


def set_strategy_param_set_activation(
    conn: sqlite3.Connection,
    *,
    param_set_id: int,
    is_active: int,
    updated_at: str,
    activated_at: str | None,
    deactivated_at: str | None,
) -> None:
    conn.execute(
        """
        UPDATE strategy_param_sets
        SET is_active = ?, updated_at = ?, activated_at = ?, deactivated_at = ?
        WHERE id = ?
        """,
        (
            int(is_active),
            updated_at,
            activated_at,
            deactivated_at,
            int(param_set_id),
        ),
    )
    conn.commit()


def close_active_sleeve_strategy_assignment(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    effective_to: str,
    updated_at: str,
) -> None:
    conn.execute(
        """
        UPDATE sleeve_strategy_assignments
        SET is_incumbent = 0,
            effective_to = ?,
            updated_at = ?
        WHERE sleeve_id = ?
          AND is_incumbent = 1
          AND effective_to IS NULL
        """,
        (effective_to, updated_at, int(sleeve_id)),
    )
    conn.commit()


def insert_sleeve_strategy_assignment(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    strategy_name: str,
    param_set_id: int | None,
    effective_from: str,
    effective_to: str | None,
    is_incumbent: int,
    created_at: str,
    updated_at: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO sleeve_strategy_assignments (
            sleeve_id,
            strategy_name,
            param_set_id,
            effective_from,
            effective_to,
            is_incumbent,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(sleeve_id),
            strategy_name,
            None if param_set_id is None else int(param_set_id),
            effective_from,
            effective_to,
            int(is_incumbent),
            created_at,
            updated_at,
        ),
    )
    conn.commit()
    if cursor.lastrowid is None:
        raise ValueError("Expected sleeve_strategy_assignments id after insert.")
    return int(cursor.lastrowid)


def fetch_active_sleeve_strategy_assignment(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM sleeve_strategy_assignments
        WHERE sleeve_id = ?
          AND is_incumbent = 1
          AND effective_to IS NULL
        ORDER BY effective_from DESC, id DESC
        LIMIT 1
        """,
        (int(sleeve_id),),
    ).fetchone()


def fetch_sleeve_strategy_assignments(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM sleeve_strategy_assignments
        WHERE sleeve_id = ?
        ORDER BY effective_from DESC, id DESC
        """,
        (int(sleeve_id),),
    ).fetchall()
