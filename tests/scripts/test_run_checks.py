from __future__ import annotations

import sys

import scripts.run_checks as run_checks


def test_run_checks_defaults_to_quick(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["scripts.run_checks"])

    args = run_checks.parse_args()

    assert args.command == "quick"


def test_run_checks_accepts_aggregate_commands(monkeypatch) -> None:
    for command in ("docs", "repo", "python", "quick", "ci"):
        monkeypatch.setattr(sys, "argv", ["scripts.run_checks", command])

        args = run_checks.parse_args()

        assert args.command == command
