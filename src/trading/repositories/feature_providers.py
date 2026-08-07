from __future__ import annotations

import sqlite3

from trading.models.strategy import FeatureProviderRecord
from trading.persistence.unit_of_work import commit_unit_of_work


class FeatureProviderRepository:
    """SQL access for the feature_providers catalog (enablement is data; fetch logic is code)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> FeatureProviderRecord:
        return FeatureProviderRecord.from_mapping(dict(row))

    def upsert(
        self,
        *,
        provider_key: str,
        enabled: int,
        config_json: str | None = None,
        created_at: str,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO feature_providers (provider_key, enabled, config_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(provider_key) DO UPDATE SET
                enabled = excluded.enabled,
                config_json = excluded.config_json,
                updated_at = excluded.updated_at
            """,
            (provider_key, enabled, config_json, created_at, updated_at),
        )
        commit_unit_of_work(self._conn)

    def fetch_by_key(self, *, provider_key: str) -> FeatureProviderRecord | None:
        row = self._conn.execute(
            "SELECT * FROM feature_providers WHERE provider_key = ?",
            (provider_key,),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def fetch_enabled(self) -> list[FeatureProviderRecord]:
        rows = self._conn.execute(
            "SELECT * FROM feature_providers WHERE enabled = 1 ORDER BY provider_key ASC"
        ).fetchall()
        return [self._row_to_record(row) for row in rows]
