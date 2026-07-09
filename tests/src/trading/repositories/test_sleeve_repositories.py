from __future__ import annotations

import pytest

from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.repositories.sleeves import SleeveRepository
from trading.repositories.strategy_param_sets import StrategyParamSetRepository


class _StaticCursor:
    def __init__(self, *, lastrowid=None, row=None, rowcount=1) -> None:
        self.lastrowid = lastrowid
        self.rowcount = rowcount
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


class _StaticConnection:
    def __init__(self, *results) -> None:
        self._results = list(results)
        self.commits = 0

    def execute(self, *_args, **_kwargs):
        if not self._results:
            raise AssertionError("Unexpected execute call")
        return self._results.pop(0)

    def commit(self) -> None:
        self.commits += 1


class TestSleevesRepository:
    def test_insert_fetch_and_update_sleeve(self, conn, account_id, sleeve_id) -> None:
        repo = SleeveRepository(conn)

        sleeve = repo.fetch_by_id(sleeve_id=sleeve_id)
        assert sleeve is not None
        assert sleeve.name == "core"
        assert sleeve.current_cash == 10_000.0

        repo.update_status(sleeve_id=sleeve_id, status="paused", updated_at="2026-05-04T00:00:00Z")
        repo.update_balances(
            sleeve_id=sleeve_id,
            current_cash=9_100.0,
            current_equity=9_500.0,
            updated_at="2026-05-04T00:00:00Z",
        )

        updated = repo.fetch_by_id(sleeve_id=sleeve_id)
        assert updated is not None
        assert updated.status == "paused"
        assert updated.current_cash == 9_100.0
        assert updated.current_equity == 9_500.0

        all_sleeves = repo.fetch_for_account(account_id=account_id)
        assert [s.id for s in all_sleeves] == [sleeve_id]

    def test_update_trade_universes_can_set_and_clear_override(self, conn, sleeve_id) -> None:
        repo = SleeveRepository(conn)
        repo.update_trade_universes(
            sleeve_id=sleeve_id,
            trade_universes='["SPY","QQQ"]',
            updated_at="2026-05-05T00:00:00Z",
        )
        updated = repo.fetch_by_id(sleeve_id=sleeve_id)
        assert updated is not None
        assert updated.trade_universes == '["SPY","QQQ"]'

        repo.update_trade_universes(
            sleeve_id=sleeve_id,
            trade_universes=None,
            updated_at="2026-05-05T01:00:00Z",
        )
        cleared = repo.fetch_by_id(sleeve_id=sleeve_id)
        assert cleared is not None
        assert cleared.trade_universes is None
        assert cleared.updated_at == "2026-05-05T01:00:00Z"

    def test_insert_sleeve_raises_when_lastrowid_missing(self) -> None:
        with pytest.raises(ValueError, match="Expected strategy_sleeves id after insert"):
            SleeveRepository(_StaticConnection(_StaticCursor(lastrowid=None))).insert(
                account_id=1,
                name="core",
                status="active",
                base_ccy="USD",
                start_equity=1000.0,
                current_cash=1000.0,
                current_equity=1000.0,
                created_at="2026-05-03T00:00:00Z",
                updated_at="2026-05-03T00:00:00Z",
            )

    def test_param_sets_and_assignments(self, conn, account_id, sleeve_id) -> None:
        sleeve_repo = SleeveRepository(conn)
        param_repo = StrategyParamSetRepository(conn)

        param_set_id = param_repo.insert(
            strategy_name="trend",
            version="v1",
            params_json='{"lookback":20}',
            config_version="cfg-1",
            is_active=0,
            created_at="2026-05-03T00:00:00Z",
            updated_at="2026-05-03T00:00:00Z",
            activated_at=None,
            deactivated_at=None,
            notes=None,
        )
        param_repo.set_activation(
            param_set_id=param_set_id,
            is_active=1,
            updated_at="2026-05-03T01:00:00Z",
            activated_at="2026-05-03T01:00:00Z",
            deactivated_at=None,
        )

        active = param_repo.fetch_active(strategy_name="trend")
        assert active is not None
        assert active.id == param_set_id

        inserted = param_repo.fetch_by_id(param_set_id=param_set_id)
        assert inserted is not None
        assert inserted.version == "v1"

        first_assignment_id = sleeve_repo.insert_assignment(
            sleeve_id=sleeve_id,
            strategy_name="trend",
            param_set_id=param_set_id,
            effective_from="2026-05-03T02:00:00Z",
            effective_to=None,
            is_incumbent=1,
            created_at="2026-05-03T02:00:00Z",
            updated_at="2026-05-03T02:00:00Z",
        )
        assert first_assignment_id > 0

        sleeve_repo.close_active_assignment(
            sleeve_id=sleeve_id,
            effective_to="2026-05-04T00:00:00Z",
            updated_at="2026-05-04T00:00:00Z",
        )

        sleeve_repo.insert_assignment(
            sleeve_id=sleeve_id,
            strategy_name="meanrev",
            param_set_id=None,
            effective_from="2026-05-04T00:00:00Z",
            effective_to=None,
            is_incumbent=1,
            created_at="2026-05-04T00:00:00Z",
            updated_at="2026-05-04T00:00:00Z",
        )

        active_assignment = sleeve_repo.fetch_active_assignment(sleeve_id=sleeve_id)
        assert active_assignment is not None
        assert active_assignment.strategy_name == "meanrev"

        all_assignments = sleeve_repo.fetch_assignments(sleeve_id=sleeve_id)
        assert len(all_assignments) == 2

    def test_insert_param_set_and_assignment_raise_when_lastrowid_missing(self) -> None:
        with pytest.raises(ValueError, match="Expected strategy_param_sets id after insert"):
            StrategyParamSetRepository(_StaticConnection(_StaticCursor(lastrowid=None))).insert(
                strategy_name="trend",
                version="v1",
                params_json='{"lookback": 20}',
                config_version=None,
                is_active=0,
                created_at="2026-05-03T00:00:00Z",
                updated_at="2026-05-03T00:00:00Z",
                activated_at=None,
                deactivated_at=None,
                notes=None,
            )

        with pytest.raises(ValueError, match="Expected sleeve_strategy_assignments id after insert"):
            SleeveRepository(_StaticConnection(_StaticCursor(lastrowid=None))).insert_assignment(
                sleeve_id=1,
                strategy_name="trend",
                param_set_id=None,
                effective_from="2026-05-03T00:00:00Z",
                effective_to=None,
                is_incumbent=1,
                created_at="2026-05-03T00:00:00Z",
                updated_at="2026-05-03T00:00:00Z",
            )


class TestRotationDecisionsAndMetricsRepositories:
    def test_rotation_decisions_and_metrics(self, conn, account_id, sleeve_id) -> None:
        decision_id = RotationDecisionRepository(conn).insert(
            sleeve_id=sleeve_id,
            decision_time="2026-05-03T15:00:00Z",
            incumbent_strategy="trend",
            challenger_strategy="meanrev",
            selected_strategy="trend",
            rotation_action="hold",
            cooldown_active=0,
            score_components_json='{"a":1}',
            gate_results_json='{"ok":true}',
            decision_reason="threshold_not_met",
            config_version="cfg-z",
            param_set_id=None,
            created_at="2026-05-03T15:00:00Z",
        )
        assert decision_id > 0
        repo = RotationDecisionRepository(conn)
        latest = repo.fetch_latest(sleeve_id=sleeve_id)
        assert latest is not None
        assert latest["rotation_action"] == "hold"
        history = repo.fetch_for_sleeve(sleeve_id=sleeve_id, limit=5)
        assert len(history) == 1
        assert repo.fetch_latest_rotate_action(sleeve_id=sleeve_id) is None

        RotationDecisionRepository(conn).insert(
            sleeve_id=sleeve_id,
            decision_time="2026-05-03T16:00:00Z",
            incumbent_strategy="trend",
            challenger_strategy="meanrev",
            selected_strategy="meanrev",
            rotation_action="rotate",
            cooldown_active=0,
            score_components_json='{"a":2}',
            gate_results_json='{"ok":true}',
            decision_reason="rotate_to_challenger",
            config_version="cfg-z",
            param_set_id=None,
            created_at="2026-05-03T16:00:00Z",
        )
        latest_rotate = RotationDecisionRepository(conn).fetch_latest_rotate_action(sleeve_id=sleeve_id)
        assert latest_rotate is not None
        assert latest_rotate["rotation_action"] == "rotate"

        sleeve_metric_id = DailyMetricsRepository(conn).upsert(
            account_id=account_id,
            sleeve_id=sleeve_id,
            metric_date="2026-05-03",
            return_pct=1.2,
            drawdown_pct=-0.4,
            turnover_pct=3.0,
            slippage_bps=4.5,
            hit_rate=0.6,
            expectancy=0.12,
            risk_adjusted_score=1.1,
            trade_count=2,
            fees_total=3.5,
            created_at="2026-05-03T23:59:00Z",
            updated_at="2026-05-03T23:59:00Z",
        )
        sleeve_metric_id_updated = DailyMetricsRepository(conn).upsert(
            account_id=account_id,
            sleeve_id=sleeve_id,
            metric_date="2026-05-03",
            return_pct=1.3,
            drawdown_pct=-0.3,
            turnover_pct=3.1,
            slippage_bps=4.0,
            hit_rate=0.62,
            expectancy=0.15,
            risk_adjusted_score=1.2,
            trade_count=3,
            fees_total=3.9,
            created_at="2026-05-03T23:59:00Z",
            updated_at="2026-05-04T00:01:00Z",
        )
        assert sleeve_metric_id_updated == sleeve_metric_id

        portfolio_metric_id = DailyMetricsRepository(conn).upsert(
            account_id=account_id,
            sleeve_id=None,
            metric_date="2026-05-03",
            return_pct=0.8,
            drawdown_pct=-0.2,
            turnover_pct=2.0,
            slippage_bps=3.0,
            hit_rate=0.55,
            expectancy=0.1,
            risk_adjusted_score=0.9,
            trade_count=4,
            fees_total=5.0,
            created_at="2026-05-03T23:59:00Z",
            updated_at="2026-05-03T23:59:00Z",
        )
        portfolio_metric_id_updated = DailyMetricsRepository(conn).upsert(
            account_id=account_id,
            sleeve_id=None,
            metric_date="2026-05-03",
            return_pct=0.9,
            drawdown_pct=-0.15,
            turnover_pct=2.1,
            slippage_bps=2.8,
            hit_rate=0.56,
            expectancy=0.11,
            risk_adjusted_score=0.95,
            trade_count=5,
            fees_total=5.2,
            created_at="2026-05-03T23:59:00Z",
            updated_at="2026-05-04T00:01:00Z",
        )
        assert portfolio_metric_id_updated == portfolio_metric_id

        metrics_repo = DailyMetricsRepository(conn)
        account_metrics = metrics_repo.fetch_for_account(account_id=account_id, limit=10)
        assert len(account_metrics) == 2
        sleeve_metrics = metrics_repo.fetch_for_sleeve(sleeve_id=sleeve_id, limit=10)
        assert len(sleeve_metrics) == 1
        sleeve_window_metrics = metrics_repo.fetch_for_sleeve_window(
            sleeve_id=sleeve_id,
            start_date="2026-05-03",
            end_date="2026-05-03",
        )
        assert len(sleeve_window_metrics) == 1


class TestLegacyBridgeGuardPaths:
    def test_insert_guard_paths_for_rotation_and_metrics(self) -> None:
        sleeve_row = {
            "account_id": 1,
            "name": "core",
            "start_equity": 100.0,
            "current_cash": 100.0,
            "current_equity": 100.0,
            "created_at": "2026-05-03T00:00:00Z",
        }
        with pytest.raises(ValueError, match="Expected rotation_decisions id after insert"):
            RotationDecisionRepository(
                _StaticConnection(
                    _StaticCursor(row=sleeve_row),  # sleeve lookup
                    _StaticCursor(row=None),  # books lookup misses
                    _StaticCursor(lastrowid=5),  # bridging-book insert
                    _StaticCursor(lastrowid=None),  # decision insert fails
                )
            ).insert(
                sleeve_id=1,
                decision_time="2026-05-03T00:00:00Z",
                incumbent_strategy=None,
                challenger_strategy=None,
                selected_strategy=None,
                rotation_action="hold",
                cooldown_active=0,
                score_components_json="{}",
                gate_results_json="{}",
                decision_reason=None,
                config_version=None,
                param_set_id=None,
                created_at="2026-05-03T00:00:00Z",
            )

        with pytest.raises(ValueError, match="Expected daily_metrics id after upsert"):
            DailyMetricsRepository(
                _StaticConnection(
                    _StaticCursor(row=None),  # default-book lookup misses
                    _StaticCursor(lastrowid=7),  # bootstrap default book
                    _StaticCursor(),  # metrics upsert
                    _StaticCursor(row=None),  # id read-back fails
                )
            ).upsert(
                account_id=1,
                sleeve_id=None,
                metric_date="2026-05-03",
                return_pct=None,
                drawdown_pct=None,
                turnover_pct=None,
                slippage_bps=None,
                hit_rate=None,
                expectancy=None,
                risk_adjusted_score=None,
                trade_count=None,
                fees_total=None,
                created_at="2026-05-03T00:00:00Z",
                updated_at="2026-05-03T00:00:00Z",
            )
