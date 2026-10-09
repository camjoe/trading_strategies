from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from fastapi import HTTPException
from paper_trading_web.backend.services import catalog_runner
from paper_trading_web.backend.services.catalog_runner import build_command, load_catalog, run_entry

from trading.domain.exceptions import NotFoundError, ValidationError


def _argument(dest: str, **overrides: Any) -> dict[str, Any]:
    argument: dict[str, Any] = {
        "flags": [f"--{dest.replace('_', '-')}"],
        "dest": dest,
        "scope": "command",
        "positional": False,
        "kind": "value",
        "type": "str",
        "required": False,
        "default": None,
        "choices": None,
        "help": "",
    }
    argument.update(overrides)
    return argument


def _entry(arguments: list[dict[str, Any]], argv: list[str] | None = None, **overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": "demo",
        "risk": "read-only",
        "runnable": True,
        "argv": argv or ["-c", "print('ok')"],
        "subcommand": None,
        "arguments": arguments,
    }
    entry.update(overrides)
    return entry


def _args(entry: dict[str, Any], values: dict[str, Any]) -> list[str]:
    """The arguments after the entry's own ``argv``."""
    return build_command(entry, values)[len(entry["argv"]) :]


class TestBuildArguments:
    def test_options_use_the_equals_form_so_a_value_cannot_become_another_option(self) -> None:
        entry = _entry([_argument("account", required=True)])

        assert _args(entry, {"account": "--force"}) == ["--account=--force"]

    def test_omits_optional_arguments_left_empty(self) -> None:
        entry = _entry([_argument("account", required=True), _argument("book"), _argument("limit", type="int")])

        assert _args(entry, {"account": "alpha", "book": "", "limit": None}) == ["--account=alpha"]

    def test_requires_required_arguments(self) -> None:
        with pytest.raises(ValidationError, match="account is required"):
            _args(_entry([_argument("account", required=True)]), {})

    def test_rejects_unknown_arguments(self) -> None:
        with pytest.raises(ValidationError, match="Unknown arguments for demo: shell"):
            _args(_entry([_argument("account")]), {"shell": "rm -rf /"})

    @pytest.mark.parametrize(("type_name", "bad"), [("int", "3.5"), ("int", "abc"), ("float", "x")])
    def test_checks_numeric_types(self, type_name: str, bad: str) -> None:
        with pytest.raises(ValidationError, match=f"must be a {type_name}"):
            _args(_entry([_argument("n", type=type_name)]), {"n": bad})

    def test_accepts_numbers(self) -> None:
        entry = _entry([_argument("n", type="int"), _argument("x", type="float")])

        assert _args(entry, {"n": 20, "x": "0.5"}) == ["--n=20", "--x=0.5"]

    def test_enforces_choices(self) -> None:
        entry = _entry([_argument("format", choices=["text", "json"])])

        assert _args(entry, {"format": "json"}) == ["--format=json"]
        with pytest.raises(ValidationError, match="must be one of: text, json"):
            _args(entry, {"format": "xml"})

    def test_flags_need_a_true_value(self) -> None:
        entry = _entry([_argument("dry_run", kind="flag", type="flag")])

        assert _args(entry, {"dry_run": True}) == ["--dry-run"]
        assert _args(entry, {"dry_run": False}) == []
        with pytest.raises(ValidationError, match="true or false"):
            _args(entry, {"dry_run": "yes"})

    def test_repeatable_arguments_repeat_the_flag(self) -> None:
        entry = _entry([_argument("note", kind="repeatable")])

        assert _args(entry, {"note": ["a=1", "b=2"]}) == ["--note=a=1", "--note=b=2"]

    def test_global_options_go_before_the_subcommand_and_command_options_after_it(self) -> None:
        entry = _entry(
            [
                _argument("database", scope="global", required=True),
                _argument("revision", scope="command", positional=True, flags=["revision"]),
                _argument("limit", scope="command", type="int"),
            ],
            argv=["-m", "tool"],
            subcommand="status",
        )

        command = build_command(entry, {"database": "x.db", "revision": "head", "limit": 3})

        assert command == ["-m", "tool", "--database=x.db", "status", "--limit=3", "head"]

    def test_a_subcommand_without_global_options_still_follows_the_module(self) -> None:
        entry = _entry([], argv=["-m", "tool"], subcommand="history")

        assert build_command(entry, {}) == ["-m", "tool", "history"]

    def test_positionals_follow_the_options_and_cannot_start_with_a_dash(self) -> None:
        entry = _entry(
            [
                _argument("target", positional=True, flags=["target"], required=True),
                _argument("account"),
            ]
        )

        assert _args(entry, {"target": "head", "account": "a"}) == ["--account=a", "head"]
        with pytest.raises(ValidationError, match="must not start with '-'"):
            _args(entry, {"target": "-x"})

    @pytest.mark.parametrize("bad", ["a\nb", "a\x00b", ["list"], {"k": "v"}])
    def test_rejects_multiline_or_structured_values(self, bad: object) -> None:
        with pytest.raises(ValidationError):
            _args(_entry([_argument("account")]), {"account": bad})


class TestRunEntry:
    def test_runs_a_runnable_entry_and_returns_its_output(self) -> None:
        result = run_entry("demo", {}, catalog={"demo": _entry([])})

        assert result["exitCode"] == 0
        assert result["output"].strip() == "ok"
        assert result["timedOut"] is False
        assert result["truncated"] is False
        assert result["command"].startswith("python -c")

    def test_reports_a_failing_exit_code_and_merges_stderr(self) -> None:
        entry = _entry([], argv=["-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"])

        result = run_entry("demo", {}, catalog={"demo": entry})

        assert result["exitCode"] == 3
        assert "out" in result["output"]
        assert "err" in result["output"]

    def test_passes_validated_values_to_the_command(self) -> None:
        entry = _entry([_argument("word", required=True)], argv=["-c", "import sys; print(sys.argv[1])"])

        result = run_entry("demo", {"word": "hello world"}, catalog={"demo": entry})

        assert result["output"].strip() == "--word=hello world"
        assert "'--word=hello world'" in result["command"]

    def test_stops_a_command_that_runs_too_long(self) -> None:
        entry = _entry([], argv=["-c", "import time; time.sleep(30)"])

        result = run_entry("demo", {}, catalog={"demo": entry}, timeout_seconds=1)

        assert result["timedOut"] is True
        assert result["exitCode"] is None

    def test_truncates_long_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(catalog_runner, "MAX_OUTPUT_CHARS", 10)
        entry = _entry([], argv=["-c", "print('x' * 100)"])

        result = run_entry("demo", {}, catalog={"demo": entry})

        assert result["truncated"] is True
        assert len(result["output"]) == 10

    def test_does_not_use_a_shell(self) -> None:
        entry = _entry([_argument("word")], argv=["-c", "import sys; print(sys.argv[1])"])

        result = run_entry("demo", {"word": "a; echo injected && echo more"}, catalog={"demo": entry})

        assert result["output"].strip() == "--word=a; echo injected && echo more"

    def test_a_missing_catalog_file_reports_how_to_regenerate_it(self, tmp_path) -> None:
        with pytest.raises(HTTPException) as caught:
            load_catalog(tmp_path / "missing.json")

        assert caught.value.status_code == 503
        assert "documentation_ui.sync" in caught.value.detail

    def test_unknown_entry_is_not_found(self) -> None:
        with pytest.raises(NotFoundError):
            run_entry("missing", {}, catalog={})

    def test_entry_that_is_not_runnable_is_refused(self) -> None:
        entry = _entry([], runnable=False, risk="writes-local")

        with pytest.raises(ValidationError, match="cannot be run from the UI"):
            run_entry("demo", {}, catalog={"demo": entry})

    def test_second_run_while_one_is_active_gets_a_conflict(self) -> None:
        started = threading.Event()
        slow = _entry([], argv=["-c", "import time; time.sleep(3)"])
        results: list[dict[str, Any]] = []

        def first() -> None:
            started.set()
            results.append(run_entry("demo", {}, catalog={"demo": slow}))

        worker = threading.Thread(target=first)
        worker.start()
        started.wait()
        for _ in range(100):
            if catalog_runner._run_lock.locked():
                break
            time.sleep(0.05)

        with pytest.raises(HTTPException) as caught:
            run_entry("demo", {}, catalog={"demo": _entry([])})
        worker.join()

        assert caught.value.status_code == 409
        assert results[0]["exitCode"] == 0

    def test_lock_is_released_after_a_run(self) -> None:
        run_entry("demo", {}, catalog={"demo": _entry([])})

        assert not catalog_runner._run_lock.locked()


class TestRealCatalog:
    def test_every_runnable_entry_is_read_only_and_assembles_from_placeholder_values(self) -> None:
        catalog = load_catalog()
        runnable = [entry for entry in catalog.values() if entry["runnable"]]

        assert len(runnable) > 20
        for entry in runnable:
            assert entry["risk"] == "read-only", entry["name"]
            assert entry["argv"][0] == "-m", entry["name"]
            values = {
                argument["dest"]: (argument["choices"][0] if argument["choices"] else "x")
                for argument in entry["arguments"]
                if argument["required"] and argument["kind"] != "flag"
            }
            for argument in entry["arguments"]:
                if argument["type"] in {"int", "float"} and argument["required"]:
                    values[argument["dest"]] = "1"
            build_command(entry, values)

    def test_no_writing_or_broker_entry_is_runnable(self) -> None:
        for entry in load_catalog().values():
            if entry["risk"] != "read-only":
                assert entry["runnable"] is False, entry["name"]

    def test_runs_a_real_read_only_command(self) -> None:
        result = run_entry("describe-db-schema", {})

        assert result["exitCode"] == 0, result["output"]
        assert "accounts" in result["output"]
        assert result["command"].startswith("python -m scripts.data_ops.describe_db_schema")
