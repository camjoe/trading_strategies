from __future__ import annotations

import pytest

from trading.repositories.strategy_param_sets import StrategyParamSetRepository


def _insert(
    conn,
    *,
    strategy_name: str = "trend",
    version: str = "v1",
    is_active: int = 0,
    params_json: str = "{}",
) -> int:
    return StrategyParamSetRepository(conn).insert(
        strategy_name=strategy_name,
        version=version,
        params_json=params_json,
        config_version=None,
        is_active=is_active,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        activated_at=None,
        deactivated_at=None,
        notes=None,
    )


class TestInsert:
    def test_returns_positive_id(self, conn) -> None:
        assert _insert(conn) > 0

    def test_raises_when_lastrowid_missing(self) -> None:
        class _Cursor:
            lastrowid = None

            def fetchone(self):
                return None

            def fetchall(self):
                return []

        class _Conn:
            def execute(self, *_a, **_kw):
                return _Cursor()

            def commit(self):
                pass

        with pytest.raises(ValueError, match="Expected strategy_param_sets id after insert"):
            StrategyParamSetRepository(_Conn()).insert(
                strategy_name="trend",
                version="v1",
                params_json="{}",
                config_version=None,
                is_active=0,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
                activated_at=None,
                deactivated_at=None,
                notes=None,
            )


class TestFetchById:
    def test_returns_none_for_unknown_id(self, conn) -> None:
        assert StrategyParamSetRepository(conn).fetch_by_id(param_set_id=9999) is None

    def test_returns_correct_record(self, conn) -> None:
        param_set_id = _insert(conn, strategy_name="momentum", version="v2", params_json='{"k": 1}')
        record = StrategyParamSetRepository(conn).fetch_by_id(param_set_id=param_set_id)
        assert record is not None
        assert record.id == param_set_id
        assert record.strategy_name == "momentum"
        assert record.version == "v2"
        assert record.params_json == '{"k": 1}'

    def test_optional_fields_default_to_none(self, conn) -> None:
        param_set_id = _insert(conn)
        record = StrategyParamSetRepository(conn).fetch_by_id(param_set_id=param_set_id)
        assert record is not None
        assert record.config_version is None
        assert record.activated_at is None
        assert record.deactivated_at is None
        assert record.notes is None


class TestFetchActive:
    def test_returns_none_when_no_active_param_set(self, conn) -> None:
        _insert(conn, strategy_name="trend", is_active=0)
        assert StrategyParamSetRepository(conn).fetch_active(strategy_name="trend") is None

    def test_returns_active_param_set(self, conn) -> None:
        repo = StrategyParamSetRepository(conn)
        param_set_id = _insert(conn, strategy_name="trend", is_active=1)
        record = repo.fetch_active(strategy_name="trend")
        assert record is not None
        assert record.id == param_set_id
        assert record.is_active == 1

    def test_returns_none_for_different_strategy(self, conn) -> None:
        _insert(conn, strategy_name="trend", is_active=1)
        assert StrategyParamSetRepository(conn).fetch_active(strategy_name="meanrev") is None

    def test_returns_most_recently_updated_when_multiple_active(self, conn) -> None:
        repo = StrategyParamSetRepository(conn)
        repo.insert(
            strategy_name="trend",
            version="v1",
            params_json="{}",
            config_version=None,
            is_active=1,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            activated_at=None,
            deactivated_at=None,
            notes=None,
        )
        id_latest = repo.insert(
            strategy_name="trend",
            version="v2",
            params_json="{}",
            config_version=None,
            is_active=1,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-02T00:00:00Z",
            activated_at=None,
            deactivated_at=None,
            notes=None,
        )
        record = repo.fetch_active(strategy_name="trend")
        assert record is not None
        assert record.id == id_latest


class TestSetActivation:
    def test_activates_inactive_param_set(self, conn) -> None:
        repo = StrategyParamSetRepository(conn)
        param_set_id = _insert(conn, is_active=0)
        repo.set_activation(
            param_set_id=param_set_id,
            is_active=1,
            updated_at="2026-01-02T00:00:00Z",
            activated_at="2026-01-02T00:00:00Z",
            deactivated_at=None,
        )
        record = repo.fetch_by_id(param_set_id=param_set_id)
        assert record is not None
        assert record.is_active == 1
        assert record.activated_at == "2026-01-02T00:00:00Z"
        assert record.updated_at == "2026-01-02T00:00:00Z"

    def test_deactivates_active_param_set(self, conn) -> None:
        repo = StrategyParamSetRepository(conn)
        param_set_id = _insert(conn, is_active=1)
        repo.set_activation(
            param_set_id=param_set_id,
            is_active=0,
            updated_at="2026-01-03T00:00:00Z",
            activated_at=None,
            deactivated_at="2026-01-03T00:00:00Z",
        )
        record = repo.fetch_by_id(param_set_id=param_set_id)
        assert record is not None
        assert record.is_active == 0
        assert record.deactivated_at == "2026-01-03T00:00:00Z"
        assert repo.fetch_active(strategy_name="trend") is None
