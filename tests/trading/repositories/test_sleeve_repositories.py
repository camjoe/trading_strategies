from __future__ import annotations

import pytest

from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.portfolio_risk_snapshots import PortfolioRiskSnapshotRepository
from trading.repositories.rotation_decisions import (
    fetch_latest_rotate_decision_for_sleeve,
    fetch_latest_rotation_decision_for_sleeve,
    fetch_rotation_decisions_for_sleeve,
    fetch_rotation_decisions_for_sleeve_date,
    insert_rotation_decision,
)
from trading.repositories.sleeve_ledger import (
    fetch_sleeve_ledger_entries,
    fetch_sleeve_ledger_sum_by_type,
    insert_sleeve_ledger_entry,
)
from trading.repositories.sleeve_orders import (
    attach_sleeve_order_broker_order_id,
    fetch_open_sleeve_orders_for_account,
    fetch_sleeve_fills_for_order,
    fetch_sleeve_order_by_broker_order_id,
    fetch_sleeve_order_by_id,
    fetch_sleeve_orders_for_sleeve,
    insert_sleeve_fill,
    insert_sleeve_order,
    update_sleeve_order_status,
)
from trading.repositories.sleeve_positions import (
    delete_sleeve_position,
    fetch_sleeve_position,
    fetch_sleeve_positions,
    fetch_sleeve_positions_for_account,
    upsert_sleeve_position,
)
from trading.repositories.sleeve_risk_decisions import (
    fetch_sleeve_risk_decisions_for_account,
    fetch_sleeve_risk_decisions_for_account_date,
    insert_sleeve_risk_decision,
)
from trading.repositories.sleeves import (
    close_active_sleeve_strategy_assignment,
    fetch_active_sleeve_strategy_assignment,
    fetch_active_strategy_param_set,
    fetch_sleeve_strategy_assignments,
    fetch_strategy_param_set_by_id,
    fetch_strategy_sleeve_by_id,
    fetch_strategy_sleeves_for_account,
    insert_sleeve_strategy_assignment,
    insert_strategy_param_set,
    insert_strategy_sleeve,
    set_strategy_param_set_activation,
    update_sleeve_trade_universes,
    update_strategy_sleeve_balances,
    update_strategy_sleeve_status,
)


class _StaticCursor:
    def __init__(self, *, lastrowid=None, row=None) -> None:
        self.lastrowid = lastrowid
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

        row = fetch_strategy_sleeve_by_id(conn, sleeve_id=sleeve_id)
        assert row is not None
        assert row["name"] == "core"
        assert float(row["current_cash"]) == 10_000.0

        update_strategy_sleeve_status(
            conn,
            sleeve_id=sleeve_id,
            status="paused",
            updated_at="2026-05-04T00:00:00Z",
        )
        update_strategy_sleeve_balances(
            conn,
            sleeve_id=sleeve_id,
            current_cash=9_100.0,
            current_equity=9_500.0,
            updated_at="2026-05-04T00:00:00Z",
        )

        updated = fetch_strategy_sleeve_by_id(conn, sleeve_id=sleeve_id)
        assert updated is not None
        assert updated["status"] == "paused"
        assert float(updated["current_cash"]) == 9_100.0
        assert float(updated["current_equity"]) == 9_500.0

        rows = fetch_strategy_sleeves_for_account(conn, account_id=account_id)
        assert [int(item["id"]) for item in rows] == [sleeve_id]

    def test_update_trade_universes_can_set_and_clear_override(self, conn, sleeve_id) -> None:
        update_sleeve_trade_universes(
            conn,
            sleeve_id=sleeve_id,
            trade_universes='["SPY","QQQ"]',
            updated_at="2026-05-05T00:00:00Z",
        )
        updated = fetch_strategy_sleeve_by_id(conn, sleeve_id=sleeve_id)
        assert updated is not None
        assert updated["trade_universes"] == '["SPY","QQQ"]'

        update_sleeve_trade_universes(
            conn,
            sleeve_id=sleeve_id,
            trade_universes=None,
            updated_at="2026-05-05T01:00:00Z",
        )
        cleared = fetch_strategy_sleeve_by_id(conn, sleeve_id=sleeve_id)
        assert cleared is not None
        assert cleared["trade_universes"] is None
        assert cleared["updated_at"] == "2026-05-05T01:00:00Z"

    def test_insert_strategy_sleeve_raises_when_lastrowid_missing(self) -> None:
        conn = _StaticConnection(_StaticCursor(lastrowid=None))

        with pytest.raises(ValueError, match="Expected strategy_sleeves id after insert"):
            insert_strategy_sleeve(
                conn,
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

        param_set_id = insert_strategy_param_set(
            conn,
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
        set_strategy_param_set_activation(
            conn,
            param_set_id=param_set_id,
            is_active=1,
            updated_at="2026-05-03T01:00:00Z",
            activated_at="2026-05-03T01:00:00Z",
            deactivated_at=None,
        )

        active = fetch_active_strategy_param_set(conn, strategy_name="trend")
        assert active is not None
        assert int(active["id"]) == param_set_id

        inserted = fetch_strategy_param_set_by_id(conn, param_set_id=param_set_id)
        assert inserted is not None
        assert inserted["version"] == "v1"

        first_assignment_id = insert_sleeve_strategy_assignment(
            conn,
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

        close_active_sleeve_strategy_assignment(
            conn,
            sleeve_id=sleeve_id,
            effective_to="2026-05-04T00:00:00Z",
            updated_at="2026-05-04T00:00:00Z",
        )

        insert_sleeve_strategy_assignment(
            conn,
            sleeve_id=sleeve_id,
            strategy_name="meanrev",
            param_set_id=None,
            effective_from="2026-05-04T00:00:00Z",
            effective_to=None,
            is_incumbent=1,
            created_at="2026-05-04T00:00:00Z",
            updated_at="2026-05-04T00:00:00Z",
        )

        active_assignment = fetch_active_sleeve_strategy_assignment(conn, sleeve_id=sleeve_id)
        assert active_assignment is not None
        assert active_assignment["strategy_name"] == "meanrev"

        all_assignments = fetch_sleeve_strategy_assignments(conn, sleeve_id=sleeve_id)
        assert len(all_assignments) == 2

    def test_insert_param_set_and_assignment_raise_when_lastrowid_missing(self) -> None:
        with pytest.raises(ValueError, match="Expected strategy_param_sets id after insert"):
            insert_strategy_param_set(
                _StaticConnection(_StaticCursor(lastrowid=None)),
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
            insert_sleeve_strategy_assignment(
                _StaticConnection(_StaticCursor(lastrowid=None)),
                sleeve_id=1,
                strategy_name="trend",
                param_set_id=None,
                effective_from="2026-05-03T00:00:00Z",
                effective_to=None,
                is_incumbent=1,
                created_at="2026-05-03T00:00:00Z",
                updated_at="2026-05-03T00:00:00Z",
            )


class TestSleeveOrdersRepository:
    def test_insert_update_and_query_sleeve_orders(self, conn, account_id, sleeve_id) -> None:

        order_id = insert_sleeve_order(
            conn,
            account_id=account_id,
            sleeve_id=sleeve_id,
            strategy_name="trend",
            param_set_id=None,
            rotation_decision_id=None,
            broker_order_id=None,
            symbol="SPY",
            side="buy",
            qty=10,
            order_type="market",
            time_in_force="day",
            requested_price=500.0,
            status="Submitted",
            config_version="cfg-a",
            submitted_at="2026-05-03T10:00:00Z",
            updated_at="2026-05-03T10:00:00Z",
        )
        attach_sleeve_order_broker_order_id(
            conn,
            sleeve_order_id=order_id,
            broker_order_id="ib-100",
            updated_at="2026-05-03T10:01:00Z",
        )
        update_sleeve_order_status(
            conn,
            sleeve_order_id=order_id,
            status="Filled",
            updated_at="2026-05-03T10:02:00Z",
        )

        row = fetch_sleeve_order_by_id(conn, sleeve_order_id=order_id)
        assert row is not None
        assert row["broker_order_id"] == "ib-100"
        assert row["status"] == "Filled"

        sleeve_rows = fetch_sleeve_orders_for_sleeve(conn, sleeve_id=sleeve_id)
        assert len(sleeve_rows) == 1

        open_rows = fetch_open_sleeve_orders_for_account(conn, account_id=account_id)
        assert len(open_rows) == 0

    def test_fill_insert_is_idempotent_for_exec_id(self, conn, account_id, sleeve_id) -> None:
        order_id = insert_sleeve_order(
            conn,
            account_id=account_id,
            sleeve_id=sleeve_id,
            strategy_name="trend",
            param_set_id=None,
            rotation_decision_id=None,
            broker_order_id="ib-200",
            symbol="QQQ",
            side="buy",
            qty=5,
            order_type="market",
            time_in_force="day",
            requested_price=420.0,
            status="Submitted",
            config_version=None,
            submitted_at="2026-05-03T11:00:00Z",
            updated_at="2026-05-03T11:00:00Z",
        )
        insert_sleeve_fill(
            conn,
            sleeve_order_id=order_id,
            sleeve_id=sleeve_id,
            broker_fill_id="fill-1",
            exec_id="exec-1",
            symbol="QQQ",
            filled_qty=5,
            fill_price=421.0,
            commission=1.2,
            fill_time="2026-05-03T11:01:00Z",
        )
        insert_sleeve_fill(
            conn,
            sleeve_order_id=order_id,
            sleeve_id=sleeve_id,
            broker_fill_id="fill-1",
            exec_id="exec-1",
            symbol="QQQ",
            filled_qty=5,
            fill_price=421.0,
            commission=1.2,
            fill_time="2026-05-03T11:01:00Z",
        )
        fills = fetch_sleeve_fills_for_order(conn, sleeve_order_id=order_id)
        assert len(fills) == 1

    def test_fetch_by_broker_order_id_returns_matching_account_row(self, conn, account_id, sleeve_id) -> None:
        insert_sleeve_order(
            conn,
            account_id=account_id,
            sleeve_id=sleeve_id,
            strategy_name="trend",
            param_set_id=None,
            rotation_decision_id=None,
            broker_order_id="ib-300",
            symbol="SPY",
            side="buy",
            qty=1,
            order_type="market",
            time_in_force="day",
            requested_price=500.0,
            status="Submitted",
            config_version=None,
            submitted_at="2026-05-03T09:00:00Z",
            updated_at="2026-05-03T09:00:00Z",
        )

        row = fetch_sleeve_order_by_broker_order_id(conn, account_id=account_id, broker_order_id="ib-300")

        assert row is not None
        assert row["broker_order_id"] == "ib-300"
        assert int(row["account_id"]) == account_id
        assert fetch_sleeve_order_by_broker_order_id(conn, account_id=account_id, broker_order_id="missing") is None

    def test_insert_sleeve_order_raises_when_lastrowid_missing(self) -> None:
        with pytest.raises(ValueError, match="Expected sleeve_orders id after insert"):
            insert_sleeve_order(
                _StaticConnection(_StaticCursor(lastrowid=None)),
                account_id=1,
                sleeve_id=1,
                strategy_name="trend",
                param_set_id=None,
                rotation_decision_id=None,
                broker_order_id=None,
                symbol="SPY",
                side="buy",
                qty=1,
                order_type="market",
                time_in_force="day",
                requested_price=500.0,
                status="Submitted",
                config_version=None,
                submitted_at="2026-05-03T09:00:00Z",
                updated_at="2026-05-03T09:00:00Z",
            )


class TestSleevePositionsLedgerDecisionsAndMetrics:
    def test_positions_ledger_decisions_and_metrics(self, conn, account_id, sleeve_id) -> None:

        upsert_sleeve_position(
            conn,
            sleeve_id=sleeve_id,
            symbol="IWM",
            qty=4,
            avg_cost=200.0,
            market_value=810.0,
            unrealized_pnl=10.0,
            updated_at="2026-05-03T12:00:00Z",
        )
        upsert_sleeve_position(
            conn,
            sleeve_id=sleeve_id,
            symbol="IWM",
            qty=6,
            avg_cost=205.0,
            market_value=1_250.0,
            unrealized_pnl=20.0,
            updated_at="2026-05-03T13:00:00Z",
        )

        one = fetch_sleeve_position(conn, sleeve_id=sleeve_id, symbol="IWM")
        assert one is not None
        assert float(one["qty"]) == 6.0

        many = fetch_sleeve_positions(conn, sleeve_id=sleeve_id)
        assert len(many) == 1
        joined = fetch_sleeve_positions_for_account(conn, account_id=account_id)
        assert len(joined) == 1

        insert_sleeve_ledger_entry(
            conn,
            sleeve_id=sleeve_id,
            entry_type="fee",
            amount=-1.5,
            reference_type="order",
            reference_id="1",
            entry_time="2026-05-03T13:30:00Z",
            created_at="2026-05-03T13:30:00Z",
        )
        insert_sleeve_ledger_entry(
            conn,
            sleeve_id=sleeve_id,
            entry_type="fee",
            amount=-2.0,
            reference_type="order",
            reference_id="2",
            entry_time="2026-05-03T14:00:00Z",
            created_at="2026-05-03T14:00:00Z",
        )
        entries = fetch_sleeve_ledger_entries(conn, sleeve_id=sleeve_id, limit=10)
        assert len(entries) == 2
        fee_total = fetch_sleeve_ledger_sum_by_type(
            conn,
            sleeve_id=sleeve_id,
            entry_type="fee",
        )
        assert fee_total == -3.5

        decision_id = insert_rotation_decision(
            conn,
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
        latest = fetch_latest_rotation_decision_for_sleeve(conn, sleeve_id=sleeve_id)
        assert latest is not None
        assert latest["rotation_action"] == "hold"
        history = fetch_rotation_decisions_for_sleeve(conn, sleeve_id=sleeve_id, limit=5)
        assert len(history) == 1
        assert fetch_latest_rotate_decision_for_sleeve(conn, sleeve_id=sleeve_id) is None

        insert_rotation_decision(
            conn,
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
        latest_rotate = fetch_latest_rotate_decision_for_sleeve(conn, sleeve_id=sleeve_id)
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

        repo = DailyMetricsRepository(conn)
        account_metrics = repo.fetch_for_account(account_id=account_id, limit=10)
        assert len(account_metrics) == 2
        sleeve_metrics = repo.fetch_for_sleeve(sleeve_id=sleeve_id, limit=10)
        assert len(sleeve_metrics) == 1
        sleeve_window_metrics = repo.fetch_for_sleeve_window(
            sleeve_id=sleeve_id,
            start_date="2026-05-03",
            end_date="2026-05-03",
        )
        assert len(sleeve_window_metrics) == 1

        delete_sleeve_position(conn, sleeve_id=sleeve_id, symbol="IWM")
        removed = fetch_sleeve_position(conn, sleeve_id=sleeve_id, symbol="IWM")
        assert removed is None


class TestPortfolioRiskSnapshotsRepository:
    def test_upsert_and_fetch_latest_snapshot(self, conn, account_id) -> None:

        PortfolioRiskSnapshotRepository(conn).upsert(
            account_id=account_id,
            snapshot_time="2026-05-03T10:00:00Z",
            gross_exposure=1000.0,
            net_exposure=400.0,
            max_symbol_concentration_pct=0.2,
            max_sector_concentration_pct=0.0,
            drawdown_pct=None,
            leverage_proxy=None,
            daily_loss_pct=None,
            kill_switch_triggered=0,
            risk_payload_json='{"a":1}',
        )
        PortfolioRiskSnapshotRepository(conn).upsert(
            account_id=account_id,
            snapshot_time="2026-05-03T10:00:00Z",
            gross_exposure=1100.0,
            net_exposure=450.0,
            max_symbol_concentration_pct=0.25,
            max_sector_concentration_pct=0.0,
            drawdown_pct=None,
            leverage_proxy=None,
            daily_loss_pct=None,
            kill_switch_triggered=1,
            risk_payload_json='{"a":2}',
        )
        PortfolioRiskSnapshotRepository(conn).upsert(
            account_id=account_id,
            snapshot_time="2026-05-03T11:00:00Z",
            gross_exposure=1200.0,
            net_exposure=500.0,
            max_symbol_concentration_pct=0.3,
            max_sector_concentration_pct=0.0,
            drawdown_pct=None,
            leverage_proxy=None,
            daily_loss_pct=None,
            kill_switch_triggered=0,
            risk_payload_json='{"a":3}',
        )

        latest = PortfolioRiskSnapshotRepository(conn).fetch_latest(account_id=account_id)
        assert latest is not None
        assert latest.snapshot_time == "2026-05-03T11:00:00Z"
        assert latest.gross_exposure == 1200.0

        updated_same_time = conn.execute(
            """
            SELECT gross_exposure, kill_switch_triggered, risk_payload_json
            FROM portfolio_risk_snapshots
            WHERE account_id = ? AND snapshot_time = ?
            """,
            (account_id, "2026-05-03T10:00:00Z"),
        ).fetchone()
        assert updated_same_time is not None
        assert float(updated_same_time["gross_exposure"]) == 1100.0
        assert int(updated_same_time["kill_switch_triggered"]) == 1
        assert updated_same_time["risk_payload_json"] == '{"a":2}'


class TestSleeveRiskDecisionsRepository:
    def test_insert_and_fetch_sleeve_risk_decisions(self, conn, account_id, sleeve_id) -> None:

        insert_sleeve_risk_decision(
            conn,
            account_id=account_id,
            sleeve_id=sleeve_id,
            decision_time="2026-05-03T10:00:00Z",
            symbol="AAPL",
            side="buy",
            action="rescale",
            reason_code="sleeve_notional_cap",
            requested_qty=5,
            approved_qty=2,
            requested_notional=500.0,
            approved_notional=200.0,
            execution_mode="sleeve",
            risk_payload_json='{"x":1}',
            created_at="2026-05-03T10:00:00Z",
        )
        insert_sleeve_risk_decision(
            conn,
            account_id=account_id,
            sleeve_id=None,
            decision_time="2026-05-03T11:00:00Z",
            symbol=None,
            side=None,
            action="block",
            reason_code="stale_price_data",
            requested_qty=None,
            approved_qty=None,
            requested_notional=None,
            approved_notional=None,
            execution_mode="sleeve",
            risk_payload_json='{"y":2}',
            created_at="2026-05-03T11:00:00Z",
        )

        rows = fetch_sleeve_risk_decisions_for_account(conn, account_id=account_id, limit=10)
        assert len(rows) == 2
        assert rows[0]["reason_code"] == "stale_price_data"
        assert rows[1]["reason_code"] == "sleeve_notional_cap"

    def test_date_scoped_fetches_and_guard_paths(self, conn, account_id, sleeve_id) -> None:
        insert_rotation_decision(
            conn,
            sleeve_id=sleeve_id,
            decision_time="2026-05-02T23:59:00Z",
            incumbent_strategy="trend",
            challenger_strategy="meanrev",
            selected_strategy="trend",
            rotation_action="hold",
            cooldown_active=0,
            score_components_json='{"a":0}',
            gate_results_json='{"ok":true}',
            decision_reason="before-window",
            config_version=None,
            param_set_id=None,
            created_at="2026-05-02T23:59:00Z",
        )
        insert_rotation_decision(
            conn,
            sleeve_id=sleeve_id,
            decision_time="2026-05-03T09:00:00Z",
            incumbent_strategy="trend",
            challenger_strategy="meanrev",
            selected_strategy="meanrev",
            rotation_action="rotate",
            cooldown_active=0,
            score_components_json='{"a":1}',
            gate_results_json='{"ok":true}',
            decision_reason="in-window",
            config_version=None,
            param_set_id=None,
            created_at="2026-05-03T09:00:00Z",
        )
        insert_rotation_decision(
            conn,
            sleeve_id=sleeve_id,
            decision_time="2026-05-04T00:00:00Z",
            incumbent_strategy="meanrev",
            challenger_strategy="trend",
            selected_strategy="meanrev",
            rotation_action="hold",
            cooldown_active=0,
            score_components_json='{"a":2}',
            gate_results_json='{"ok":true}',
            decision_reason="after-window",
            config_version=None,
            param_set_id=None,
            created_at="2026-05-04T00:00:00Z",
        )

        rotation_rows = fetch_rotation_decisions_for_sleeve_date(
            conn,
            sleeve_id=sleeve_id,
            report_date="2026-05-03",
        )
        assert [row["decision_reason"] for row in rotation_rows] == ["in-window"]

        insert_sleeve_risk_decision(
            conn,
            account_id=account_id,
            sleeve_id=sleeve_id,
            decision_time="2026-05-02T23:59:00Z",
            symbol="AAPL",
            side="buy",
            action="block",
            reason_code="before-window",
            requested_qty=1,
            approved_qty=0,
            requested_notional=100.0,
            approved_notional=0.0,
            execution_mode="sleeve",
            risk_payload_json='{"k":0}',
            created_at="2026-05-02T23:59:00Z",
        )
        insert_sleeve_risk_decision(
            conn,
            account_id=account_id,
            sleeve_id=None,
            decision_time="2026-05-03T10:30:00Z",
            symbol=None,
            side=None,
            action="rescale",
            reason_code="in-window",
            requested_qty=None,
            approved_qty=None,
            requested_notional=None,
            approved_notional=None,
            execution_mode="account",
            risk_payload_json='{"k":1}',
            created_at="2026-05-03T10:30:00Z",
        )
        insert_sleeve_risk_decision(
            conn,
            account_id=account_id,
            sleeve_id=None,
            decision_time="2026-05-04T00:00:00Z",
            symbol=None,
            side=None,
            action="block",
            reason_code="after-window",
            requested_qty=None,
            approved_qty=None,
            requested_notional=None,
            approved_notional=None,
            execution_mode="account",
            risk_payload_json='{"k":2}',
            created_at="2026-05-04T00:00:00Z",
        )

        risk_rows = fetch_sleeve_risk_decisions_for_account_date(
            conn,
            account_id=account_id,
            report_date="2026-05-03",
        )
        assert [row["reason_code"] for row in risk_rows] == ["in-window"]

        assert (
            fetch_sleeve_ledger_sum_by_type(
                _StaticConnection(_StaticCursor(row=None)),
                sleeve_id=1,
                entry_type="fee",
            )
            == 0.0
        )

        with pytest.raises(ValueError, match="Expected sleeve_ledger id after insert"):
            insert_sleeve_ledger_entry(
                _StaticConnection(_StaticCursor(lastrowid=None)),
                sleeve_id=1,
                entry_type="fee",
                amount=-1.0,
                reference_type="order",
                reference_id="1",
                entry_time="2026-05-03T00:00:00Z",
                created_at="2026-05-03T00:00:00Z",
            )

        with pytest.raises(ValueError, match="Expected sleeve_risk_decisions id after insert"):
            insert_sleeve_risk_decision(
                _StaticConnection(_StaticCursor(lastrowid=None)),
                account_id=1,
                sleeve_id=None,
                decision_time="2026-05-03T00:00:00Z",
                symbol=None,
                side=None,
                action="block",
                reason_code="guard",
                requested_qty=None,
                approved_qty=None,
                requested_notional=None,
                approved_notional=None,
                execution_mode="account",
                risk_payload_json="{}",
                created_at="2026-05-03T00:00:00Z",
            )

        with pytest.raises(ValueError, match="Expected rotation_decisions id after insert"):
            insert_rotation_decision(
                _StaticConnection(_StaticCursor(lastrowid=None)),
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

        with pytest.raises(ValueError, match="Expected daily_metrics id after insert"):
            DailyMetricsRepository(
                _StaticConnection(_StaticCursor(row=None), _StaticCursor(lastrowid=None))
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
