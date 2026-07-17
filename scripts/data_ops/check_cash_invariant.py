"""Cash invariant check: books.current_cash reconciles with the ledger sum.

Every book is created with ``current_cash = start_equity``, and every later
cash change writes matching ledger rows (a fill's ``trade`` + ``fee`` entries
sum to its cash delta; deposits/withdrawals are signed amounts). So for each
book, ``current_cash - start_equity`` must equal ``SUM(ledger.amount)`` within
a float tolerance — money is stored as REAL (see docs/reference/db-schema.md,
"Money as REAL"). Divergence beyond the tolerance surfaces as a report row and
a non-zero exit instead of a silent drift.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from infrastructure.database.config import get_db_path

DEFAULT_TOLERANCE = 0.01

_BOOK_CASH_QUERY = """
SELECT b.id AS book_id, b.name AS book_name, a.name AS account_name,
       b.start_equity, b.current_cash,
       COALESCE(SUM(l.amount), 0.0) AS ledger_sum
FROM books b
JOIN accounts a ON a.id = b.account_id
LEFT JOIN ledger l ON l.book_id = b.id
GROUP BY b.id
ORDER BY a.name, b.name
"""


def _connect_live() -> sqlite3.Connection:
    db_path = get_db_path()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def invariant_payload(
    conn: sqlite3.Connection,
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    db_path: Path | None = None,
) -> dict[str, Any]:
    books: list[dict[str, Any]] = []
    for row in conn.execute(_BOOK_CASH_QUERY):
        expected = float(row["start_equity"]) + float(row["ledger_sum"])
        divergence = float(row["current_cash"]) - expected
        books.append(
            {
                "book_id": int(row["book_id"]),
                "book_name": str(row["book_name"]),
                "account_name": str(row["account_name"]),
                "start_equity": float(row["start_equity"]),
                "current_cash": float(row["current_cash"]),
                "ledger_sum": float(row["ledger_sum"]),
                "divergence": divergence,
                "ok": abs(divergence) <= tolerance,
            }
        )
    return {
        "db_path": str(db_path) if db_path is not None else None,
        "tolerance": tolerance,
        "books": books,
        "divergent": [book for book in books if not book["ok"]],
    }


def _print_text(payload: dict[str, Any]) -> None:
    print("Cash Invariant Check")
    if payload["db_path"]:
        print(f"Database path: {payload['db_path']}")
    print(f"Tolerance: {payload['tolerance']}")
    print(f"Books checked: {len(payload['books'])}")
    divergent = payload["divergent"]
    print(f"Divergent books: {len(divergent)}")

    for book in divergent:
        print(
            f"- {book['account_name']}/{book['book_name']} (book {book['book_id']}): "
            f"current_cash {book['current_cash']:.6f} != "
            f"start_equity {book['start_equity']:.6f} + ledger sum {book['ledger_sum']:.6f} "
            f"(divergence {book['divergence']:+.6f})"
        )

    if divergent:
        print("\nFAIL: cash does not reconcile with the ledger for the books above.")
    else:
        print("\nPASS: every book's cash reconciles with its ledger.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that each book's current_cash reconciles with start_equity plus its ledger sum.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help=f"Maximum absolute divergence to accept (default {DEFAULT_TOLERANCE}).",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = _connect_live()
    try:
        payload = invariant_payload(conn, tolerance=args.tolerance, db_path=get_db_path())
    finally:
        conn.close()

    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_text(payload)
    return 1 if payload["divergent"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
