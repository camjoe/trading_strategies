from pathlib import Path
from types import SimpleNamespace

from trading.interfaces.cli import main as cli_main
from tests.support.cli_main import install_main_harness


def test_main_init_prints_initialized_path(monkeypatch, capsys) -> None:
    fake_conn = install_main_harness(monkeypatch, cli_main, SimpleNamespace(command="init"))

    cli_main.main()

    out = capsys.readouterr().out
    assert "Initialized:" in out
    assert fake_conn.closed is True


def test_main_apply_account_profiles_passes_create_missing(monkeypatch, capsys) -> None:
    args = SimpleNamespace(command="apply-account-profiles", file="custom_profiles.json", no_create_missing=True)
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}

    monkeypatch.setattr(cli_main, "load_account_profiles", lambda path: captured.update({"path": path}) or [{"name": "acct1"}])
    monkeypatch.setattr(
        cli_main,
        "apply_account_profiles",
        lambda conn, profiles, *, create_missing: captured.update(
            {"conn": conn, "profiles": profiles, "create_missing": create_missing}
        ) or (1, 2, 3),
    )

    cli_main.main()

    assert captured["path"] == "custom_profiles.json"
    assert captured["create_missing"] is False
    assert "Applied account profiles: created=1, updated=2, skipped=3." in capsys.readouterr().out
    assert fake_conn.closed is True


def test_main_apply_account_preset_uses_lowercased_filename(monkeypatch, capsys) -> None:
    args = SimpleNamespace(command="apply-account-preset", preset="Conservative", no_create_missing=False)
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}

    monkeypatch.setattr(cli_main, "load_account_profiles", lambda path: captured.update({"path": path}) or [{"name": "acct1"}])
    monkeypatch.setattr(
        cli_main,
        "apply_account_profiles",
        lambda conn, profiles, *, create_missing: captured.update(
            {"conn": conn, "profiles": profiles, "create_missing": create_missing}
        ) or (0, 1, 0),
    )

    cli_main.main()

    assert Path(captured["path"]).as_posix().endswith("account_profiles/conservative.json")
    assert captured["create_missing"] is True
    assert "Applied preset 'Conservative': created=0, updated=1, skipped=0." in capsys.readouterr().out
    assert fake_conn.closed is True


def test_main_report_dispatches(monkeypatch) -> None:
    args = SimpleNamespace(command="report", account="acct1")
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}
    monkeypatch.setattr(
        cli_main,
        "account_report",
        lambda conn, account: captured.update({"conn": conn, "account": account}),
    )

    cli_main.main()

    assert captured == {"conn": fake_conn, "account": "acct1"}
    assert fake_conn.closed is True


def test_main_snapshot_dispatches(monkeypatch) -> None:
    args = SimpleNamespace(command="snapshot", account="acct1", time="2026-03-21T10:15:00")
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}
    monkeypatch.setattr(
        cli_main,
        "snapshot_account",
        lambda conn, account, snap_time: captured.update(
            {"conn": conn, "account": account, "snap_time": snap_time}
        ),
    )

    cli_main.main()

    assert captured == {"conn": fake_conn, "account": "acct1", "snap_time": "2026-03-21T10:15:00"}
    assert fake_conn.closed is True


def test_main_snapshot_history_dispatches(monkeypatch) -> None:
    args = SimpleNamespace(command="snapshot-history", account="acct1", limit=25)
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}
    monkeypatch.setattr(
        cli_main,
        "show_snapshots",
        lambda conn, account, limit: captured.update({"conn": conn, "account": account, "limit": limit}),
    )

    cli_main.main()

    assert captured == {"conn": fake_conn, "account": "acct1", "limit": 25}
    assert fake_conn.closed is True


def test_main_compare_strategies_dispatches(monkeypatch) -> None:
    args = SimpleNamespace(command="compare-strategies", lookback=60)
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}
    monkeypatch.setattr(
        cli_main,
        "compare_strategies",
        lambda conn, lookback: captured.update({"conn": conn, "lookback": lookback}),
    )

    cli_main.main()

    assert captured == {"conn": fake_conn, "lookback": 60}
    assert fake_conn.closed is True
