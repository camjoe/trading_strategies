from __future__ import annotations

import sys

import scripts.run_checks as run_checks


def test_run_checks_defaults_to_quick(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["scripts.run_checks"])

    args = run_checks.parse_args()

    assert args.command == "quick"


def test_run_checks_accepts_aggregate_commands(monkeypatch) -> None:
    for command in ("docs", "repo", "python", "quick", "ci", "pr"):
        monkeypatch.setattr(sys, "argv", ["scripts.run_checks", command])

        args = run_checks.parse_args()

        assert args.command == command


def test_run_checks_pr_defaults_to_develop_and_accepts_a_base(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["scripts.run_checks", "pr"])
    assert run_checks.parse_args().base_ref == "develop"

    monkeypatch.setattr(sys, "argv", ["scripts.run_checks", "pr", "--base", "main", "--no-cov"])
    args = run_checks.parse_args()

    assert args.base_ref == "main"
    assert args.no_cov is True
