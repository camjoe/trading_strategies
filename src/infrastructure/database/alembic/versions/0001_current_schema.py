"""Create the complete current schema.

Revision ID: 0001
Revises: None (base)

Immutable and self-contained by convention (docs/reference/db-migration-system.md):
no imports from application code, and every value required by the DDL is a
literal frozen at authoring time. This revision is the squashed baseline: it
reproduces the head shape of the retired 0001-0031 chain in one CREATE, minus
the unused ``feature_providers`` table (dropped as part of the squash).
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Tables in creation order (SQLite does not validate FK targets at CREATE time,
# so forward references to later tables are allowed).
_TABLES: tuple[tuple[str, str], ...] = (
    (
        "accounts",
        """
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            base_ccy TEXT NOT NULL DEFAULT 'USD',
            initial_cash REAL NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            benchmark_ticker TEXT NOT NULL DEFAULT 'SPY',
            descriptive_name TEXT NOT NULL DEFAULT '',
            broker_type TEXT NOT NULL DEFAULT 'paper',
            broker_host TEXT,
            broker_port INTEGER,
            broker_client_id INTEGER,
            live_trading_enabled INTEGER NOT NULL DEFAULT 0
        )
        """,
    ),
    (
        "strategies",
        """
        CREATE TABLE strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_key TEXT NOT NULL UNIQUE,
            primitive TEXT NOT NULL,
            params_json TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'frozen', 'retired')),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    ),
    (
        "global_settings",
        """
        CREATE TABLE global_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            runtime_max_trades_per_day INTEGER CHECK (
                runtime_max_trades_per_day IS NULL OR runtime_max_trades_per_day >= 1
            ),
            runtime_max_trades_per_minute INTEGER CHECK (
                runtime_max_trades_per_minute IS NULL OR runtime_max_trades_per_minute >= 1
            ),
            evaluation_backtest_trade_count_for_full_confidence INTEGER CHECK (
                evaluation_backtest_trade_count_for_full_confidence IS NULL
                OR evaluation_backtest_trade_count_for_full_confidence >= 1
            ),
            evaluation_backtest_snapshot_count_for_full_confidence INTEGER CHECK (
                evaluation_backtest_snapshot_count_for_full_confidence IS NULL
                OR evaluation_backtest_snapshot_count_for_full_confidence >= 1
            ),
            evaluation_paper_live_snapshot_count_for_full_confidence INTEGER CHECK (
                evaluation_paper_live_snapshot_count_for_full_confidence IS NULL
                OR evaluation_paper_live_snapshot_count_for_full_confidence >= 1
            ),
            evaluation_backtest_trade_confidence_weight REAL CHECK (
                evaluation_backtest_trade_confidence_weight IS NULL
                OR evaluation_backtest_trade_confidence_weight BETWEEN 0 AND 1
            ),
            evaluation_backtest_snapshot_confidence_weight REAL CHECK (
                evaluation_backtest_snapshot_confidence_weight IS NULL
                OR evaluation_backtest_snapshot_confidence_weight BETWEEN 0 AND 1
            ),
            evaluation_backtest_evidence_weight REAL CHECK (
                evaluation_backtest_evidence_weight IS NULL
                OR evaluation_backtest_evidence_weight BETWEEN 0 AND 1
            ),
            evaluation_paper_live_evidence_weight REAL CHECK (
                evaluation_paper_live_evidence_weight IS NULL
                OR evaluation_paper_live_evidence_weight BETWEEN 0 AND 1
            ),
            promotion_min_research_backtest_trade_count INTEGER CHECK (
                promotion_min_research_backtest_trade_count IS NULL
                OR promotion_min_research_backtest_trade_count >= 1
            ),
            promotion_min_research_backtest_snapshot_count INTEGER CHECK (
                promotion_min_research_backtest_snapshot_count IS NULL
                OR promotion_min_research_backtest_snapshot_count >= 1
            ),
            promotion_min_research_backtest_return_pct REAL,
            promotion_min_research_max_drawdown_pct REAL,
            promotion_min_research_walk_forward_average_return_pct REAL,
            promotion_min_live_paper_snapshot_count INTEGER CHECK (
                promotion_min_live_paper_snapshot_count IS NULL
                OR promotion_min_live_paper_snapshot_count >= 1
            ),
            promotion_min_live_overall_confidence REAL CHECK (
                promotion_min_live_overall_confidence IS NULL
                OR promotion_min_live_overall_confidence BETWEEN 0 AND 1
            ),
            updated_at TEXT
        )
        """,
    ),
    (
        "global_settings_change_events",
        """
        CREATE TABLE global_settings_change_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            settings_group TEXT NOT NULL,
            changed_fields TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
    ),
    (
        "books",
        """
        CREATE TABLE books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'closed')),
            is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
            start_equity REAL NOT NULL,
            current_cash REAL NOT NULL,
            current_equity REAL NOT NULL,
            trade_symbols TEXT NOT NULL,
            goal_min_return_pct REAL,
            goal_max_return_pct REAL,
            goal_period TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            learning_enabled INTEGER NOT NULL DEFAULT 0 CHECK (learning_enabled IN (0, 1)),
            risk_policy TEXT NOT NULL DEFAULT 'none' CHECK (
                risk_policy IN ('none', 'fixed_stop', 'take_profit', 'stop_and_target')
            ),
            stop_loss_pct REAL,
            take_profit_pct REAL,
            option_profit_take_pct REAL,
            option_max_loss_pct REAL,
            trade_size_pct REAL,
            max_position_pct REAL,
            max_trades_per_run INTEGER CHECK (max_trades_per_run IS NULL OR max_trades_per_run >= 1),
            instrument_mode TEXT NOT NULL DEFAULT 'equity' CHECK (instrument_mode IN ('equity', 'leaps')),
            option_strike_offset_pct REAL,
            option_min_dte INTEGER,
            option_max_dte INTEGER,
            option_type TEXT CHECK (option_type IS NULL OR option_type IN ('call', 'put', 'both')),
            target_delta_min REAL,
            target_delta_max REAL,
            max_premium_per_trade REAL,
            max_contracts_per_trade INTEGER,
            iv_rank_min REAL,
            iv_rank_max REAL,
            roll_dte_threshold INTEGER,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            UNIQUE (account_id, name)
        )
        """,
    ),
    (
        "book_rotation_settings",
        """
        CREATE TABLE book_rotation_settings (
            book_id INTEGER PRIMARY KEY,
            rotation_enabled INTEGER NOT NULL DEFAULT 0,
            rotation_lookback_days INTEGER,
            rotation_schedule TEXT,
            min_trades_in_window INTEGER,
            outperformance_threshold_bps REAL,
            cooldown_days INTEGER,
            risk_adjusted_return_weight REAL,
            stability_weight REAL,
            drawdown_penalty_weight REAL,
            regime_fit_weight REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
        )
        """,
    ),
    (
        "book_rotation_settings_change_events",
        """
        CREATE TABLE book_rotation_settings_change_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            settings_group TEXT NOT NULL,
            changed_fields TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
        )
        """,
    ),
    (
        "book_strategy_history",
        """
        CREATE TABLE book_strategy_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            strategy_id INTEGER NOT NULL,
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            FOREIGN KEY (strategy_id) REFERENCES strategies(id)
        )
        """,
    ),
    (
        "book_universe_history",
        """
        CREATE TABLE book_universe_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            trade_symbols TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
        )
        """,
    ),
    (
        "backtest_runs",
        """
        CREATE TABLE backtest_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            strategy_id INTEGER,
            run_name TEXT,
            purpose TEXT NOT NULL DEFAULT 'standalone'
                CHECK (purpose IN ('standalone', 'walk_forward_oos', 'final_holdout')),
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            slippage_bps REAL NOT NULL DEFAULT 0,
            fee_per_trade REAL NOT NULL DEFAULT 0,
            tickers_file TEXT,
            notes TEXT,
            warnings TEXT,
            benchmark_ticker TEXT,
            benchmark_return_pct REAL,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (strategy_id) REFERENCES strategies(id)
        )
        """,
    ),
    (
        "backtest_executions",
        """
        CREATE TABLE backtest_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            execution_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
            qty REAL NOT NULL,
            price REAL NOT NULL,
            fee REAL NOT NULL DEFAULT 0,
            slippage_bps REAL NOT NULL DEFAULT 0,
            note TEXT,
            FOREIGN KEY (run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
        )
        """,
    ),
    (
        "backtest_equity_snapshots",
        """
        CREATE TABLE backtest_equity_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            snapshot_date TEXT NOT NULL,
            cash REAL NOT NULL,
            market_value REAL NOT NULL,
            equity REAL NOT NULL,
            realized_pnl REAL NOT NULL,
            unrealized_pnl REAL NOT NULL,
            FOREIGN KEY (run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
        )
        """,
    ),
    (
        "rotation_decisions",
        """
        CREATE TABLE rotation_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            decision_time TEXT NOT NULL,
            incumbent_strategy_id INTEGER,
            challenger_strategy_id INTEGER,
            selected_strategy_id INTEGER,
            rotation_action TEXT NOT NULL CHECK (rotation_action IN ('hold', 'rotate')),
            cooldown_active INTEGER NOT NULL DEFAULT 0,
            score_components_json TEXT NOT NULL,
            gate_results_json TEXT NOT NULL,
            decision_reason TEXT,
            config_version TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            FOREIGN KEY (incumbent_strategy_id) REFERENCES strategies(id),
            FOREIGN KEY (challenger_strategy_id) REFERENCES strategies(id),
            FOREIGN KEY (selected_strategy_id) REFERENCES strategies(id)
        )
        """,
    ),
    (
        "orders",
        """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            strategy_id INTEGER,
            rotation_decision_id INTEGER,
            broker_order_id TEXT,
            client_order_id TEXT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
            qty REAL NOT NULL,
            order_type TEXT NOT NULL DEFAULT 'market' CHECK (order_type IN ('market', 'limit')),
            time_in_force TEXT NOT NULL DEFAULT 'day' CHECK (time_in_force IN ('day', 'gtc')),
            requested_price REAL,
            status TEXT NOT NULL CHECK (
                status IN ('pending', 'submitted', 'partially_filled', 'filled', 'rejected', 'cancelled')
            ),
            filled_qty REAL NOT NULL DEFAULT 0,
            avg_fill_price REAL,
            commission REAL NOT NULL DEFAULT 0,
            submitted_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status_reason TEXT,
            realized_pnl_delta REAL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (strategy_id) REFERENCES strategies(id),
            FOREIGN KEY (rotation_decision_id) REFERENCES rotation_decisions(id)
        )
        """,
    ),
    (
        "order_fills",
        """
        CREATE TABLE order_fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            exec_id TEXT,
            filled_qty REAL NOT NULL,
            fill_price REAL NOT NULL,
            commission REAL NOT NULL DEFAULT 0,
            fill_time TEXT NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
            UNIQUE (order_id, exec_id)
        )
        """,
    ),
    (
        "positions",
        """
        CREATE TABLE positions (
            book_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            qty REAL NOT NULL,
            avg_cost REAL NOT NULL,
            market_value REAL NOT NULL,
            unrealized_pnl REAL NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (book_id, symbol),
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
        )
        """,
    ),
    (
        "ledger",
        """
        CREATE TABLE ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            entry_type TEXT NOT NULL CHECK (
                entry_type IN ('trade', 'fee', 'deposit', 'withdrawal', 'adjustment')
            ),
            amount REAL NOT NULL,
            reference_type TEXT,
            reference_id TEXT,
            entry_time TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
        )
        """,
    ),
    (
        "equity_snapshots",
        """
        CREATE TABLE equity_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            snapshot_time TEXT NOT NULL,
            cash REAL NOT NULL,
            market_value REAL NOT NULL,
            equity REAL NOT NULL,
            realized_pnl REAL NOT NULL,
            unrealized_pnl REAL NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            UNIQUE (book_id, snapshot_time)
        )
        """,
    ),
    (
        "daily_metrics",
        """
        CREATE TABLE daily_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            metric_date TEXT NOT NULL,
            return_pct REAL,
            drawdown_pct REAL,
            turnover_pct REAL,
            slippage_bps REAL,
            hit_rate REAL,
            expectancy REAL,
            risk_adjusted_score REAL,
            trade_count INTEGER,
            fees_total REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            UNIQUE (book_id, metric_date)
        )
        """,
    ),
    (
        "risk_snapshots",
        """
        CREATE TABLE risk_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            snapshot_time TEXT NOT NULL,
            gross_exposure REAL NOT NULL,
            net_exposure REAL NOT NULL,
            max_symbol_concentration_pct REAL NOT NULL,
            max_sector_concentration_pct REAL NOT NULL,
            drawdown_pct REAL,
            leverage_proxy REAL,
            daily_loss_pct REAL,
            kill_switch_triggered INTEGER NOT NULL DEFAULT 0 CHECK (kill_switch_triggered IN (0, 1)),
            risk_payload_json TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            UNIQUE (account_id, snapshot_time)
        )
        """,
    ),
    (
        "risk_decisions",
        """
        CREATE TABLE risk_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            book_id INTEGER,
            decision_time TEXT NOT NULL,
            symbol TEXT,
            side TEXT CHECK (side IS NULL OR side IN ('buy', 'sell')),
            action TEXT NOT NULL CHECK (action IN ('allow', 'rescale', 'block')),
            reason_code TEXT NOT NULL,
            requested_qty REAL,
            approved_qty REAL,
            requested_notional REAL,
            approved_notional REAL,
            risk_payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE SET NULL,
            FOREIGN KEY (book_id, account_id) REFERENCES books(id, account_id)
        )
        """,
    ),
    (
        "promotion_reviews",
        """
        CREATE TABLE promotion_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            account_name_snapshot TEXT NOT NULL,
            strategy_name TEXT NOT NULL,
            review_state TEXT NOT NULL DEFAULT 'requested',
            assessment_stage TEXT NOT NULL,
            assessment_status TEXT NOT NULL,
            ready_for_live INTEGER NOT NULL DEFAULT 0,
            overall_confidence REAL NOT NULL DEFAULT 0,
            live_trading_enabled_snapshot INTEGER NOT NULL DEFAULT 0,
            promotion_assessment_version TEXT NOT NULL,
            evaluation_artifact_version TEXT NOT NULL,
            frozen_assessment_payload TEXT NOT NULL,
            frozen_evaluation_payload TEXT NOT NULL,
            requested_by TEXT,
            reviewed_by TEXT,
            operator_summary_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            closed_at TEXT,
            strategy_id INTEGER REFERENCES strategies(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        )
        """,
    ),
    (
        "promotion_review_events",
        """
        CREATE TABLE promotion_review_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id INTEGER NOT NULL,
            event_seq INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            actor_type TEXT NOT NULL DEFAULT 'operator',
            actor_name TEXT,
            from_review_state TEXT,
            to_review_state TEXT,
            note TEXT,
            event_payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (review_id) REFERENCES promotion_reviews(id) ON DELETE CASCADE,
            UNIQUE(review_id, event_seq)
        )
        """,
    ),
    (
        "optimization_experiments",
        """
        CREATE TABLE optimization_experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            strategy_id INTEGER,
            primitive TEXT NOT NULL,
            objective_name TEXT NOT NULL,
            search_space_json TEXT NOT NULL,
            candidate_budget INTEGER NOT NULL,
            train_months INTEGER NOT NULL,
            test_months INTEGER NOT NULL,
            step_months INTEGER NOT NULL,
            holdout_months INTEGER NOT NULL,
            warmup_months INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            window_count INTEGER NOT NULL,
            winner_params_json TEXT NOT NULL,
            oos_mean_winner_return_pct REAL,
            oos_mean_baseline_return_pct REAL,
            oos_windows_beat_baseline INTEGER,
            holdout_run_id INTEGER,
            holdout_winner_return_pct REAL,
            holdout_baseline_return_pct REAL,
            promoted_strategy_id INTEGER,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'completed',
            failure_stage TEXT,
            failure_message TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (strategy_id) REFERENCES strategies(id),
            FOREIGN KEY (holdout_run_id) REFERENCES backtest_runs(id),
            FOREIGN KEY (promoted_strategy_id) REFERENCES strategies(id)
        )
        """,
    ),
    (
        "optimization_windows",
        """
        CREATE TABLE optimization_windows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            window_index INTEGER NOT NULL,
            train_start TEXT NOT NULL,
            train_end TEXT NOT NULL,
            test_start TEXT NOT NULL,
            test_end TEXT NOT NULL,
            oos_run_id INTEGER NOT NULL,
            FOREIGN KEY (experiment_id) REFERENCES optimization_experiments(id) ON DELETE CASCADE,
            FOREIGN KEY (oos_run_id) REFERENCES backtest_runs(id)
        )
        """,
    ),
    (
        "optimization_trials",
        """
        CREATE TABLE optimization_trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            window_id INTEGER NOT NULL,
            candidate_index INTEGER NOT NULL,
            params_json TEXT NOT NULL,
            params_hash TEXT NOT NULL,
            objective_value REAL,
            annualized_return_pct REAL,
            max_drawdown_pct REAL NOT NULL,
            trade_count INTEGER NOT NULL,
            eligible INTEGER NOT NULL,
            rejection_reason TEXT,
            selected INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (window_id) REFERENCES optimization_windows(id) ON DELETE CASCADE
        )
        """,
    ),
    (
        "optimization_run_manifests",
        """
        CREATE TABLE optimization_run_manifests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            manifest_version TEXT NOT NULL,
            account_name TEXT NOT NULL,
            book_id INTEGER,
            initial_cash REAL NOT NULL,
            benchmark_ticker TEXT NOT NULL,
            slippage_bps REAL NOT NULL,
            fee_per_trade REAL NOT NULL,
            effective_execution_json TEXT NOT NULL,
            tickers_file TEXT,
            universe_history_dir TEXT,
            universe_tickers_json TEXT NOT NULL,
            universe_size INTEGER NOT NULL,
            market_data_provider TEXT NOT NULL,
            data_as_of TEXT NOT NULL,
            engine_revision TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (experiment_id) REFERENCES optimization_experiments(id) ON DELETE CASCADE,
            FOREIGN KEY (book_id) REFERENCES books(id)
        )
        """,
    ),
)

_INDEXES: tuple[str, ...] = (
    "CREATE INDEX idx_backtest_equity_run_id ON backtest_equity_snapshots(run_id)",
    "CREATE INDEX idx_backtest_executions_run_id ON backtest_executions(run_id)",
    "CREATE INDEX idx_backtest_runs_account_id ON backtest_runs(account_id)",
    (
        "CREATE INDEX idx_book_rotation_settings_change_events_book_created "
        "ON book_rotation_settings_change_events(book_id, created_at DESC)"
    ),
    "CREATE INDEX idx_book_strategy_history_book_effective ON book_strategy_history(book_id, effective_from DESC)",
    (
        "CREATE UNIQUE INDEX idx_book_strategy_history_open_per_book "
        "ON book_strategy_history(book_id) WHERE effective_to IS NULL"
    ),
    (
        "CREATE INDEX idx_book_strategy_history_strategy_effective "
        "ON book_strategy_history(strategy_id, effective_from DESC)"
    ),
    "CREATE INDEX idx_book_universe_history_book_from ON book_universe_history(book_id, effective_from DESC)",
    (
        "CREATE UNIQUE INDEX idx_book_universe_history_open_per_book "
        "ON book_universe_history(book_id) WHERE effective_to IS NULL"
    ),
    "CREATE INDEX idx_books_account_status ON books(account_id, status)",
    "CREATE UNIQUE INDEX idx_books_default_per_account ON books(account_id) WHERE is_default = 1",
    "CREATE UNIQUE INDEX idx_books_id_account ON books(id, account_id)",
    "CREATE INDEX idx_daily_metrics_book_date ON daily_metrics(book_id, metric_date DESC)",
    "CREATE INDEX idx_equity_snapshots_book_time ON equity_snapshots(book_id, snapshot_time DESC)",
    "CREATE INDEX idx_global_settings_change_events_created ON global_settings_change_events(created_at DESC)",
    "CREATE INDEX idx_ledger_book_entry_time ON ledger(book_id, entry_time DESC)",
    "CREATE INDEX idx_ledger_reference ON ledger(reference_type, reference_id)",
    (
        "CREATE INDEX idx_optimization_experiments_account_strategy_created "
        "ON optimization_experiments(account_id, strategy_id, created_at DESC)"
    ),
    "CREATE UNIQUE INDEX idx_optimization_run_manifests_experiment ON optimization_run_manifests(experiment_id)",
    (
        "CREATE UNIQUE INDEX idx_optimization_trials_selected_per_window "
        "ON optimization_trials(window_id) WHERE selected = 1"
    ),
    "CREATE UNIQUE INDEX idx_optimization_trials_window_hash ON optimization_trials(window_id, params_hash)",
    (
        "CREATE UNIQUE INDEX idx_optimization_windows_experiment_window "
        "ON optimization_windows(experiment_id, window_index)"
    ),
    "CREATE INDEX idx_order_fills_order_id ON order_fills(order_id)",
    (
        "CREATE UNIQUE INDEX idx_orders_account_broker_order_id "
        "ON orders(account_id, broker_order_id) WHERE broker_order_id IS NOT NULL"
    ),
    (
        "CREATE UNIQUE INDEX idx_orders_account_client_order_id "
        "ON orders(account_id, client_order_id) WHERE client_order_id IS NOT NULL"
    ),
    "CREATE INDEX idx_orders_account_status_submitted ON orders(account_id, status, submitted_at DESC)",
    "CREATE INDEX idx_orders_book_submitted ON orders(book_id, submitted_at DESC)",
    "CREATE INDEX idx_positions_symbol_updated ON positions(symbol, updated_at DESC)",
    "CREATE INDEX idx_promotion_review_events_review_created ON promotion_review_events(review_id, created_at ASC)",
    "CREATE INDEX idx_promotion_review_events_review_seq ON promotion_review_events(review_id, event_seq ASC)",
    (
        "CREATE INDEX idx_promotion_reviews_account_strategy_created "
        "ON promotion_reviews(account_id, strategy_name, created_at DESC)"
    ),
    (
        "CREATE UNIQUE INDEX idx_promotion_reviews_open_requested "
        "ON promotion_reviews(account_id, strategy_name) WHERE review_state = 'requested'"
    ),
    "CREATE INDEX idx_promotion_reviews_state_updated ON promotion_reviews(review_state, updated_at DESC)",
    "CREATE INDEX idx_risk_decisions_account_time ON risk_decisions(account_id, decision_time DESC)",
    "CREATE INDEX idx_risk_decisions_book_time ON risk_decisions(book_id, decision_time DESC)",
    "CREATE INDEX idx_risk_snapshots_account_time ON risk_snapshots(account_id, snapshot_time DESC)",
    "CREATE INDEX idx_rotation_decisions_action_time_book ON rotation_decisions(rotation_action, decision_time DESC)",
    "CREATE INDEX idx_rotation_decisions_book_time ON rotation_decisions(book_id, decision_time DESC)",
)

# Reverse dependency order (children before their FK targets). This is not the
# reverse of creation order: creation may forward-reference (e.g.
# equity_snapshots -> books), but drops must remove referencing tables first.
_DROP_ORDER: tuple[str, ...] = (
    "optimization_run_manifests",
    "optimization_trials",
    "optimization_windows",
    "optimization_experiments",
    "order_fills",
    "backtest_executions",
    "backtest_equity_snapshots",
    "promotion_review_events",
    "equity_snapshots",
    "daily_metrics",
    "book_rotation_settings",
    "book_rotation_settings_change_events",
    "book_strategy_history",
    "book_universe_history",
    "orders",
    "positions",
    "ledger",
    "rotation_decisions",
    "risk_snapshots",
    "risk_decisions",
    "backtest_runs",
    "promotion_reviews",
    "books",
    "strategies",
    "global_settings_change_events",
    "global_settings",
    "accounts",
)


def upgrade() -> None:
    for _table_name, create_sql in _TABLES:
        op.execute(create_sql)
    for index_sql in _INDEXES:
        op.execute(index_sql)


def downgrade() -> None:
    for table_name in _DROP_ORDER:
        op.execute(f"DROP TABLE {table_name}")
