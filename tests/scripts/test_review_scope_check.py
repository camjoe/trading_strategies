from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.checks.repo.review_scope_check import (
    LARGE_DIFF_LINES,
    NOTE_RULES,
    SCOPE_RULES,
    _numstat_entries,
    classify_paths,
    diff_stats,
    parse_args,
    run_review_scope_check,
    suggest_reviewers,
)


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


def test_docs_and_skills_are_scope_notes_not_modes() -> None:
    report = classify_paths(["docs/maps/scripts-map.md", ".ai/skills/code-review/SKILL.md"])

    assert report.modes == set()
    assert report.high_risk == []
    assert report.notes == [
        ".ai/skills/code-review/SKILL.md: skill workflow change",
        "docs/maps/scripts-map.md: documentation change",
    ]


def test_empty_changes_get_note() -> None:
    report = classify_paths([])

    assert report.changed_files == []
    assert report.modes == set()
    assert report.notes == ["No changed files detected."]


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        (
            "src/trading/services/execution/open_order_reconciliation.py",
            "order submission, fill, or reconciliation change",
        ),
        ("src/trading/services/auto_trading/runner.py", "auto-trading decision change"),
        ("src/trading/domain/auto_trading/sizing.py", "sizing or order policy change"),
        ("src/trading/domain/risk_gate.py", "risk gate change"),
        ("src/trading/domain/broker_connection.py", "broker port change"),
        ("src/trading/repositories/orders.py", "order or fill persistence change"),
        ("src/trading/repositories/ledger.py", "ledger persistence change"),
        ("src/trading/persistence/money_columns.py", "money encoding or transaction change"),
    ],
)
def test_money_paths_are_aggressive_high_risk(path: str, reason: str) -> None:
    report = classify_paths([path])

    assert "aggressive" in report.modes
    assert report.high_risk == [f"{path}: {reason}"]


def test_plan_documents_are_scope_notes_not_modes() -> None:
    report = classify_paths(["plan/review-mindsets.md"])

    assert report.modes == set()
    assert report.notes == ["plan/review-mindsets.md: plan document change"]


def _reviewer_names(paths: list[str], changed_lines: int = 0, added_modules: list[str] | None = None) -> list[str]:
    report = classify_paths(paths)
    return [name for name, _ in suggest_reviewers(report, changed_lines, added_modules)]


def test_documentation_only_diffs_get_no_reviewers() -> None:
    assert _reviewer_names(["docs/maps/scripts-map.md", ".ai/skills/code-review/SKILL.md", "README.md"]) == []
    assert _reviewer_names(["plan/review-mindsets.md"], changed_lines=900) == []


def test_empty_diffs_get_no_reviewers() -> None:
    assert _reviewer_names([]) == []


def test_ordinary_code_changes_get_the_three_base_reviewers() -> None:
    names = ["Architecture and conventions", "Break it", "Test skeptic"]

    assert _reviewer_names(["scripts/checks/pr.py"]) == names
    assert _reviewer_names(["apps/paper_trading_web/backend/routes/accounts.py"]) == names


def test_aggressive_paths_add_the_opus_sample_and_the_operator() -> None:
    assert _reviewer_names(["src/infrastructure/brokers/ibkr_web/adapter.py"]) == [
        "Architecture and conventions",
        "Break it",
        "Test skeptic",
        "Break it, second sample on Opus",
        "Operator",
    ]


def test_a_large_code_diff_adds_the_simplifier() -> None:
    below = _reviewer_names(["scripts/checks/pr.py"], changed_lines=LARGE_DIFF_LINES - 1)
    at = _reviewer_names(["scripts/checks/pr.py"], changed_lines=LARGE_DIFF_LINES)

    assert "Simplifier" not in below
    assert at[-1] == "Simplifier"


def test_a_new_module_adds_the_simplifier_with_the_module_named() -> None:
    report = classify_paths(["scripts/checks/pr.py"])

    reviewers = suggest_reviewers(report, changed_lines=10, added_modules=["scripts/checks/pr.py"])

    assert reviewers[-1] == ("Simplifier", "new module: scripts/checks/pr.py")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.test", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(tmp_path, "init", "-b", "main", str(repo))
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    _git(repo, "checkout", "-b", "feature")
    return repo


def _repo_with_broker_change(tmp_path: Path) -> Path:
    repo = _init_repo(tmp_path)
    (repo / "src" / "infrastructure" / "brokers").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / "src" / "infrastructure" / "brokers" / "adapter.py").write_text("x = 1\n" * 30, encoding="utf-8")
    (repo / "src" / "infrastructure" / "brokers" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "docs" / "note.md").write_text("doc\n" * 500, encoding="utf-8")
    (repo / "README.md").write_text("base\nchanged\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "change")
    return repo


def test_diff_stats_counts_code_lines_and_names_added_modules_but_not_documentation(tmp_path: Path) -> None:
    repo = _repo_with_broker_change(tmp_path)

    changed_lines, added_modules = diff_stats(repo, base_ref="main")

    assert changed_lines == 30
    assert added_modules == ["src/infrastructure/brokers/adapter.py"]


def test_run_review_scope_check_prints_the_suggested_reviewers(tmp_path: Path, capsys) -> None:
    repo = _repo_with_broker_change(tmp_path)

    assert run_review_scope_check(repo, base_ref="main") == 0

    output = capsys.readouterr().out
    assert "Suggested review modes: aggressive" in output
    assert "- Operator: aggressive-mode paths" in output
    assert "- Simplifier: new module: src/infrastructure/brokers/adapter.py" in output


def test_run_review_scope_check_reports_no_reviewers_for_a_documentation_only_diff(tmp_path: Path, capsys) -> None:
    repo = _init_repo(tmp_path)
    (repo / "README.md").write_text("base\nchanged\n", encoding="utf-8")
    _git(repo, "commit", "-am", "docs")

    assert run_review_scope_check(repo, base_ref="main") == 0

    assert "Suggested reviewers: none" in capsys.readouterr().out


def test_a_head_ref_is_classified_without_checking_it_out(tmp_path: Path, capsys) -> None:
    repo = _repo_with_broker_change(tmp_path)
    _git(repo, "checkout", "main")

    assert run_review_scope_check(repo, base_ref="main", head_ref="feature") == 0

    output = capsys.readouterr().out
    assert "Diff: main...feature" in output
    assert "- Operator: aggressive-mode paths" in output
    assert not (repo / "src").exists()
    assert diff_stats(repo, base_ref="main", head_ref="feature") == (30, ["src/infrastructure/brokers/adapter.py"])


def test_head_without_base_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["review_scope_check", "--head", "feature"])

    with pytest.raises(SystemExit):
        parse_args()


def test_accounting_and_starting_cash_paths_are_aggressive() -> None:
    for path in (
        "src/trading/domain/accounting/book.py",
        "src/trading/services/books/provisioning.py",
        "src/trading/services/accounts/mutations.py",
    ):
        assert "aggressive" in classify_paths([path]).modes


def test_every_scope_rule_prefix_exists_in_the_repo() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    missing = [
        rule.prefix for rule in (*SCOPE_RULES, *NOTE_RULES) if not (repo_root / rule.prefix.rstrip("/")).exists()
    ]

    assert missing == []


def test_numstat_entries_follow_a_rename_to_its_new_path_and_skip_binary_files() -> None:
    output = "5\t2\tsrc/a.py\0" + "0\t0\t\0src/old.py\0src/new.py\0" + "-\t-\timage.png\0"

    assert _numstat_entries(output) == [(5, 2, "src/a.py"), (0, 0, "src/new.py")]


def test_a_pure_rename_adds_no_changed_lines(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "old.py").write_text("x = 1\n" * 400, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "add")
    _git(repo, "checkout", "-b", "rename")
    _git(repo, "mv", "src/old.py", "src/new.py")
    _git(repo, "commit", "-am", "rename")

    assert diff_stats(repo, base_ref="feature", head_ref="rename") == (0, [])
