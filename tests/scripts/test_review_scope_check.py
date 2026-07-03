from __future__ import annotations

from scripts.checks.review_scope_check import classify_paths


def test_classifies_runtime_jobs_as_aggressive_high_risk() -> None:
    report = classify_paths(["src/trading/interfaces/runtime/jobs/daily/snapshot.py"])

    assert "aggressive" in report.modes
    assert report.high_risk == [
        "src/trading/interfaces/runtime/jobs/daily/snapshot.py: runtime job or scheduler change"
    ]


def test_classifies_cross_stack_contract_changes() -> None:
    report = classify_paths(
        [
            "apps/paper_trading_web/backend/routes/accounts.py",
            "apps/paper_trading_web/frontend/src/features/accounts/api.ts",
        ]
    )

    assert report.modes == {"contract"}
    assert report.notes == [
        "apps/paper_trading_web/backend/routes/accounts.py: backend API route change",
        "apps/paper_trading_web/frontend/src/features/accounts/api.ts: frontend API consumer change",
    ]


def test_classifies_database_changes_as_aggressive_high_risk() -> None:
    report = classify_paths(["src/infrastructure/database/schema.py"])

    assert report.modes == {"aggressive"}
    assert report.high_risk == ["src/infrastructure/database/schema.py: database schema or migration change"]


def test_defaults_to_standard_for_unmatched_changes() -> None:
    report = classify_paths(["README.md"])

    assert report.modes == {"standard"}
    assert report.high_risk == []
    assert report.notes == []


def test_empty_changes_get_note() -> None:
    report = classify_paths([])

    assert report.changed_files == []
    assert report.modes == set()
    assert report.notes == ["No changed files detected."]
