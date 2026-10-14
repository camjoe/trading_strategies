from collections.abc import Callable, Collection
from pathlib import Path

import pytest

from scripts.forge.base import RESTRICTED_SHELL, ForgeError
from scripts.forge.implement import ImplementResult, ImplementTask, run_implement_plan
from tests.scripts.test_forge import FakeSandboxes, StubForge

PLAN = "# Plan: add the thing\n\nStatus: drafted 2026-10-10. Not started.\n\n## Goal\nDo it.\n"
README = (
    "# plan/\n\n## Index\n| Plan | Status | Depends on |\n|---|---|---|\n"
    "| [thing.md](thing.md) | Drafted 2026-10-10. | none |\n"
    "| [later.md](later.md) | Drafted. | PR #9 merged |\n"
)


class FakeGit:
    def identity(self) -> tuple[str, str] | None:
        return None

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.head_value = "start000"
        self.changed: list[str] = []
        self.outgoing = ""
        self.branch_error: ForgeError | None = None
        self.committed: list[tuple[list[str], str]] = []
        self.sandbox_head: str | None = None
        self.imported: list[tuple[Path, str]] = []
        self.forwarded: list[str] = []
        self.ff_error: ForgeError | None = None
        self.discarded: list[str] = []
        self.on_base = True
        self.files: dict[str, str] = {}
        self.phase = "claim"
        self.switched: list[str] = []
        self.deleted: list[str] = []
        self.cleanup_error: ForgeError | None = None
        self.push_error: ForgeError | None = None
        self.branch_name = "develop"
        self.held: list[tuple[str, str]] = []
        self.pushed_branches: list[str] = []
        self.head_error: ForgeError | None = None

    def head(self) -> str:
        if self.head_error and "branch" in " ".join(self.calls):
            raise self.head_error
        return self.head_value

    def changed_paths(self, base: str, head: str) -> list[str]:
        return self.changed

    def outgoing_text(self, base: str, head: str) -> str:
        return self.outgoing

    def push(self, branch: str = "") -> None:
        if self.push_error:
            raise self.push_error
        self.pushed_branches.append(branch)
        self.calls.append("push" if self.phase == "agent" else "push-claim")

    def require_clean_tree(self) -> None:
        self.calls.append("clean")

    def fetch(self) -> None:
        self.calls.append("fetch")

    def create_branch(self, name: str, start: str) -> None:
        if self.branch_error:
            raise self.branch_error
        self.calls.append(f"branch {name} {start}")

    def commit_files(self, paths: Collection[Path], message: str, remove: Collection[Path] = ()) -> None:
        self.calls.append("claim")
        self.committed.append(([path.name for path in paths], message))

    def import_commits(self, source: Path, since: str) -> str:
        self.imported.append((source, since))
        head, self.sandbox_head = self.sandbox_head or self.head_value, None
        return head

    def fast_forward(self, sha: str) -> None:
        if self.ff_error:
            raise self.ff_error
        self.forwarded.append(sha)
        self.head_value = sha

    def discard_changes(self, sha: str) -> None:
        self.discarded.append(sha)

    def exists_on(self, ref: str, relative: str) -> bool:
        return self.on_base and relative in self.files

    def show(self, ref: str, relative: str) -> str:
        if relative not in self.files:
            raise ForgeError(f"{relative} is not at {ref}")
        return self.files[relative]

    def hold(self, name: str, sha: str) -> str:
        self.held.append((name, sha))
        return f"refs/forge/held/{name}/{sha[:12]}"

    def current_branch(self) -> str:
        return self.branch_name

    def switch(self, branch: str) -> None:
        if self.cleanup_error:
            raise self.cleanup_error
        self.switched.append(branch)

    def delete_branch(self, name: str) -> None:
        self.deleted.append(name)


class Setup:
    def __init__(self, tmp_path: Path) -> None:
        self.repo = tmp_path / "repo"
        (self.repo / "plan").mkdir(parents=True)
        (self.repo / "plan" / "thing.md").write_text(PLAN, encoding="utf-8")
        (self.repo / "plan" / "later.md").write_text(PLAN, encoding="utf-8")
        (self.repo / "plan" / "README.md").write_text(README, encoding="utf-8")
        self.work = tmp_path / "work"
        self.work.mkdir()
        self.git = FakeGit()
        self.git.files = {"plan/thing.md": PLAN, "plan/later.md": PLAN, "plan/README.md": README}
        self.forge = StubForge()
        self.sent: list[tuple[str, str, dict[str, object]]] = []
        self.tasks: list[ImplementTask] = []
        self.gate_result = (True, "ok")
        self.sandboxes = FakeSandboxes(self.work)
        self.gate_runs: list[Path] = []
        self.closed_when_gated: list[int] = []

    def _gate(self, cwd: Path) -> tuple[bool, str]:
        self.gate_runs.append(cwd)
        self.closed_when_gated.append(self.sandboxes.closed)
        return self.gate_result

    def agent(self, commits: bool = True, questions: str = "", fail: bool = False, summary: str = ""):
        def run(task: ImplementTask) -> None:
            self.git.calls.append("agent")
            self.git.phase = "agent"
            self.tasks.append(task)
            if fail:
                raise ForgeError("not logged in")
            if commits:
                self.git.sandbox_head = "work111"
            if questions:
                task.questions_file.write_text(questions, encoding="utf-8")
            if summary:
                task.summary_file.write_text(summary, encoding="utf-8")

        return run

    def run(self, agent: object = None, plan: str = "thing.md", **kwargs: object) -> ImplementResult:
        return run_implement_plan(
            self.forge,
            self.git,
            agent or self.agent(),  # type: ignore[arg-type]
            self.sandboxes,
            lambda base, cwd: self._gate(cwd),
            lambda subject, message, details: self.sent.append((subject, message, details)),
            self.repo,
            self.work,
            plan,
            **kwargs,  # type: ignore[arg-type]
        )


@pytest.fixture
def setup(tmp_path: Path) -> Setup:
    return Setup(tmp_path)


class TestRefusals:
    def test_a_plan_that_is_not_on_the_base_is_refused_before_any_branch_is_made(self, setup: Setup) -> None:
        result = setup.run(plan="nope.md")

        assert result.outcome == "refused" and "not on origin/develop" in result.detail
        assert setup.git.calls == ["clean", "fetch"]

    def test_a_plan_with_unconfirmed_dependencies_is_refused(self, setup: Setup) -> None:
        result = setup.run(plan="later.md")

        assert result.outcome == "refused" and "depends on" in result.detail
        assert not any(call.startswith("branch") for call in setup.git.calls) and setup.forge.opened == []

    def test_confirming_the_dependencies_lets_it_through(self, setup: Setup) -> None:
        assert setup.run(plan="later.md", depends_ok=True).outcome == "ready-for-review"

    def test_a_plan_already_in_progress_is_refused(self, setup: Setup) -> None:
        setup.git.files["plan/thing.md"] = PLAN.replace("drafted", "in progress (branch `x`)")

        assert "Already in progress" in setup.run().detail

    def test_the_plans_status_is_read_from_the_base_not_from_a_stale_checkout(self, setup: Setup) -> None:
        stale = setup.repo / "plan" / "thing.md"
        stale.write_text(PLAN, encoding="utf-8")
        setup.git.files["plan/thing.md"] = PLAN.replace("drafted", "in progress (branch `x`)")

        result = setup.run()

        assert result.outcome == "refused" and "Already in progress" in result.detail

    def test_a_branch_that_cannot_be_created_is_refused_and_no_pull_request_opens(self, setup: Setup) -> None:
        setup.git.branch_error = ForgeError("branch exists")

        result = setup.run()

        assert result.outcome == "refused" and setup.forge.opened == [] and result.branch == "feature/thing"

    def test_every_refusal_still_notifies_the_owner(self, setup: Setup) -> None:
        setup.run(plan="nope.md")

        assert len(setup.sent) == 1


class TestClaim:
    def test_the_plan_is_claimed_and_pushed_and_a_draft_opened_before_the_agent_runs(self, setup: Setup) -> None:
        setup.run()

        assert setup.git.calls[:6] == [
            "clean",
            "fetch",
            "branch feature/thing origin/develop",
            "claim",
            "push-claim",
            "agent",
        ]
        assert setup.forge.opened[0][:3] == ("develop", "feature/thing", "add the thing")
        assert setup.forge.opened[0][4] is True

    def test_the_claim_commit_changes_the_plan_and_the_index(self, setup: Setup) -> None:
        setup.run()

        assert setup.git.committed == [(["thing.md", "README.md"], "docs(plan): claim thing.md")]
        assert "in progress (branch `feature/thing`)" in (setup.repo / "plan" / "thing.md").read_text(encoding="utf-8")
        assert "In progress" not in (setup.repo / "plan" / "later.md").read_text(encoding="utf-8")
        assert "in progress (branch `feature/thing`)" in (setup.repo / "plan" / "README.md").read_text(
            encoding="utf-8"
        )


class TestRecordedOnThePullRequest:
    def test_the_summary_and_the_questions_go_in_the_description(self, setup: Setup) -> None:
        setup.run(setup.agent(questions="Which tickers?", summary="Added the universe option."))

        ((number, body),) = setup.forge.bodies
        assert number == 42
        assert "## Summary\n\nAdded the universe option." in body
        assert "## Questions for the owner\n\nWhich tickers?" in body
        assert body.startswith("Implements `plan/thing.md`")

    def test_a_summary_alone_is_recorded_on_a_clean_run(self, setup: Setup) -> None:
        setup.run(setup.agent(summary="Done."))

        assert "## Summary" in setup.forge.bodies[0][1] and "Questions" not in setup.forge.bodies[0][1]

    def test_nothing_is_written_when_the_agent_wrote_neither_file(self, setup: Setup) -> None:
        setup.run()

        assert setup.forge.bodies == []

    def test_text_with_a_local_path_or_credential_is_not_published(self, setup: Setup) -> None:
        setup.run(setup.agent(questions="See /Users/someone/repo for the file", summary="key sk-ant-abcdefghij12345"))

        assert setup.forge.bodies == []

    def test_questions_are_still_reported_to_the_owner_when_they_are_not_published(self, setup: Setup) -> None:
        result = setup.run(setup.agent(questions="See /Users/someone/repo"))

        assert result.outcome == "needs-owner" and "See /Users/someone/repo" in result.detail


class TestOutcome:
    def test_a_clean_run_pushes_and_takes_the_pull_request_out_of_draft(self, setup: Setup) -> None:
        result = setup.run()

        assert (result.outcome, result.branch, result.pr_url) == (
            "ready-for-review",
            "feature/thing",
            "https://example.test/pull/42",
        )
        assert setup.forge.ready == [42] and "push" in setup.git.calls
        assert len(setup.sent) == 1

    def test_questions_stop_it_as_a_draft_but_the_work_is_pushed(self, setup: Setup) -> None:
        result = setup.run(setup.agent(questions="Is the endpoint public?"))

        assert result.outcome == "needs-owner" and "Is the endpoint public?" in result.detail
        assert setup.forge.ready == [] and "push" in setup.git.calls

    def test_no_commits_is_no_progress(self, setup: Setup) -> None:
        result = setup.run(setup.agent(commits=False))

        assert result.outcome == "no-progress" and setup.forge.ready == []

    def test_guarded_paths_keep_it_a_draft(self, setup: Setup) -> None:
        setup.git.changed = ["src/infrastructure/brokers/ibkr.py"]

        result = setup.run()

        assert result.outcome == "needs-owner" and "guarded" in result.detail and setup.forge.ready == []

    def test_a_red_gate_keeps_it_a_draft_and_shows_the_tail(self, setup: Setup) -> None:
        setup.gate_result = (False, "FAIL: ruff")

        result = setup.run()

        assert result.outcome == "needs-owner" and "FAIL: ruff" in result.detail and setup.forge.ready == []

    def test_no_ready_leaves_a_clean_run_a_draft(self, setup: Setup) -> None:
        result = setup.run(mark_ready=False)

        assert result.outcome == "needs-owner" and setup.forge.ready == []

    def test_an_agent_failure_stops_with_the_draft_in_place(self, setup: Setup) -> None:
        result = setup.run(setup.agent(fail=True))

        assert result.outcome == "stopped" and "not logged in" in result.detail
        assert len(setup.forge.opened) == 1 and setup.forge.ready == []


class TestTaskFiles:
    def test_each_task_lists_the_files_outside_the_sandbox_that_its_prompt_names(self) -> None:
        from scripts.forge.fix_loop import RoundTask

        implement = ImplementTask("p", Path("q.md"), Path("s.md"), Path("box"))
        fix = RoundTask("p", Path("old.md"), Path("new.md"), Path("box"))

        assert implement.files == (Path("q.md"), Path("s.md"))
        assert fix.files == (Path("old.md"), Path("new.md"))


class TestPrompt:
    def test_it_names_the_plan_branch_and_files_and_forbids_pushing(self, setup: Setup) -> None:
        setup.run()

        prompt = setup.tasks[0].prompt
        assert "plan/thing.md" in prompt and "feature/thing" in prompt
        assert str(setup.tasks[0].questions_file) in prompt and str(setup.tasks[0].summary_file) in prompt
        assert "Do not push or use gh" in prompt
        assert "separate commands, never chained with `&&`" in prompt
        assert RESTRICTED_SHELL in prompt


class TestImplementPlanCommand:
    def test_a_refusal_exits_one_and_a_clean_run_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], setup: Setup
    ) -> None:
        from scripts.forge import cli as cli_module

        monkeypatch.setattr(cli_module, "get_repo_root", lambda: setup.repo)
        monkeypatch.setattr(cli_module, "LocalGit", lambda: setup.git)
        monkeypatch.setattr(cli_module, "run_claude_agent", lambda task, model=None: None)
        monkeypatch.setattr(cli_module, "run_gate", lambda base, cwd: (True, "ok"))
        monkeypatch.setattr(cli_module, "_sandbox_factory", lambda local, install=True: setup.sandboxes)
        monkeypatch.setattr(cli_module, "email_notifier", lambda subject, message, details: None)

        assert cli_module.main(["implement-plan", "--plan", "plan/nope.md"], setup.forge) == 1
        assert '"outcome": "refused"' in capsys.readouterr().out
        assert cli_module.main(["implement-plan", "--plan", "plan/thing.md", "--no-ready"], setup.forge) == 0
        assert '"outcome": "no-progress"' in capsys.readouterr().out

    def test_the_container_flag_swaps_the_gate_and_nothing_else(
        self, monkeypatch: pytest.MonkeyPatch, setup: Setup
    ) -> None:
        from scripts.forge import cli as cli_module

        gates: list[str] = []
        monkeypatch.setattr(cli_module, "get_repo_root", lambda: setup.repo)
        monkeypatch.setattr(cli_module, "LocalGit", lambda: setup.git)
        monkeypatch.setattr(cli_module, "run_claude_agent", lambda task, model=None: setup.agent()(task))

        def gate_named(name: str) -> Callable[[str, Path], tuple[bool, str]]:
            def gate(base: str, cwd: Path) -> tuple[bool, str]:
                gates.append(name)
                return True, "ok"

            return gate

        monkeypatch.setattr(cli_module, "run_gate", gate_named("host"))
        monkeypatch.setattr(cli_module.container, "run_gate", gate_named("container"))
        monkeypatch.setattr(cli_module, "_sandbox_factory", lambda local, install=True: setup.sandboxes)
        monkeypatch.setattr(cli_module, "email_notifier", lambda subject, message, details: None)

        cli_module.main(["implement-plan", "--plan", "plan/thing.md", "--no-ready", "--container"], setup.forge)

        assert gates and set(gates) == {"container"}


class TestWhatTheAgentWrites:
    def test_commits_that_contain_the_claude_token_are_held_and_never_pushed(
        self, setup: Setup, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        token = "".join(["sk", "-ant-", "oat01-", "Ab3_x-Qz9" * 8])
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", token)
        setup.git.outgoing = "+" + token[::-1]

        result = setup.run()

        assert result.outcome == "needs-owner" and "contain the Claude token" in result.detail
        assert "push" not in setup.git.calls and setup.git.forwarded == [] and setup.gate_runs == []
        assert len(setup.git.held) == 1 and token not in result.detail

    def test_commits_without_the_token_are_pushed_as_before(
        self, setup: Setup, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "".join(["sk", "-ant-", "oat01-", "Ab3_x-Qz9" * 8]))
        setup.git.outgoing = "+an ordinary change"

        result = setup.run()

        assert "push" in setup.git.calls and result.outcome != "stopped"

    def test_a_questions_file_that_is_not_a_plain_file_is_refused_not_read(self, setup: Setup) -> None:
        def agent(task: ImplementTask) -> None:
            setup.git.sandbox_head = "work111"
            task.questions_file.mkdir()

        result = setup.run(agent)

        assert result.outcome == "needs-owner" and "not a plain file" in result.detail
        assert setup.forge.ready == [] and "push" not in setup.git.calls

    def test_a_summary_file_that_is_not_a_plain_file_is_refused_not_published(self, setup: Setup) -> None:
        def agent(task: ImplementTask) -> None:
            setup.git.sandbox_head = "work111"
            task.summary_file.mkdir()

        result = setup.run(agent)

        assert result.outcome == "needs-owner" and "not a plain file" in result.detail
        assert setup.forge.ready == [] and setup.forge.bodies == []

    def test_a_bad_summary_with_a_guarded_commit_still_reports_where_the_commits_are_held(self, setup: Setup) -> None:
        setup.git.changed = ["src/infrastructure/brokers/ibkr.py"]

        def agent(task: ImplementTask) -> None:
            setup.git.sandbox_head = "work111"
            task.summary_file.mkdir()

        result = setup.run(agent)

        assert result.outcome == "needs-owner" and "not a plain file" in result.detail
        assert "refs/forge/held/" in result.detail and len(setup.git.held) == 1
        assert "push" not in setup.git.calls and setup.git.forwarded == []

    def test_a_bad_summary_with_clean_commits_holds_them_instead_of_pushing_them(self, setup: Setup) -> None:
        def agent(task: ImplementTask) -> None:
            setup.git.sandbox_head = "work111"
            task.summary_file.mkdir()

        result = setup.run(agent)

        assert "refs/forge/held/" in result.detail and len(setup.git.held) == 1
        assert "push" not in setup.git.calls and setup.gate_runs == []

    def test_a_token_in_a_changed_path_name_is_held_like_a_token_in_the_text(
        self, setup: Setup, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        token = "".join(["sk", "-ant-", "oat01-", "Ab3_x-Qz9" * 8])
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", token)
        setup.git.changed = [f"docs/{token}.md"]

        result = setup.run()

        assert "contain the Claude token" in result.detail and token not in result.detail
        assert "push" not in setup.git.calls and len(setup.git.held) == 1


class TestAgentContainerCommand:
    def _run(self, monkeypatch: pytest.MonkeyPatch, setup: Setup, *flags: str) -> list[bool]:
        from scripts.forge import cli as cli_module

        installs: list[bool] = []

        def factory(local: object, install: bool = True) -> object:
            installs.append(install)
            return setup.sandboxes

        monkeypatch.setattr(cli_module, "get_repo_root", lambda: setup.repo)
        monkeypatch.setattr(cli_module, "LocalGit", lambda: setup.git)
        monkeypatch.setattr(cli_module, "run_claude_agent", lambda task, model=None: setup.agent()(task))
        monkeypatch.setattr(
            cli_module.container, "run_agent", lambda task, model=None, identity=None: setup.agent()(task)
        )
        monkeypatch.setattr(cli_module, "run_gate", lambda base, cwd: (True, "ok"))
        monkeypatch.setattr(cli_module, "_sandbox_factory", factory)
        monkeypatch.setattr(cli_module, "email_notifier", lambda subject, message, details: None)
        cli_module.main(["implement-plan", "--plan", "plan/thing.md", "--no-ready", *flags], setup.forge)
        return installs

    def test_the_host_sandbox_builds_a_virtual_environment_by_default(
        self, monkeypatch: pytest.MonkeyPatch, setup: Setup
    ) -> None:
        assert self._run(monkeypatch, setup) == [True]

    def test_a_containerized_agent_needs_no_host_virtual_environment(
        self, monkeypatch: pytest.MonkeyPatch, setup: Setup
    ) -> None:
        assert self._run(monkeypatch, setup, "--agent-container") == [False]


class TestRefusalBeforeThePlanIsParsed:
    def test_a_missing_plan_index_is_refused_and_names_no_branch(self, setup: Setup) -> None:
        del setup.git.files["plan/README.md"]

        result = setup.run()

        assert result.outcome == "refused" and result.branch is None and "README.md" in result.detail
        assert not any(call.startswith("branch") for call in setup.git.calls) and setup.forge.opened == []


class TestPickupHardening:
    def test_a_plan_that_is_not_on_the_base_is_refused_before_any_branch_is_made(self, setup: Setup) -> None:
        setup.git.on_base = False

        result = setup.run()

        assert result.outcome == "refused" and "is not on origin/develop" in result.detail
        assert not any(call.startswith("branch") for call in setup.git.calls) and setup.forge.opened == []

    def test_a_failed_claim_push_stops_with_a_hint_to_delete_the_branch_and_still_notifies(self, setup: Setup) -> None:
        setup.git.push_error = ForgeError("rejected")

        result = setup.run()

        assert result.outcome == "stopped" and "git push origin --delete feature/thing" in result.detail
        assert setup.forge.opened == [] and len(setup.sent) == 1

    def test_a_failure_after_the_pull_request_opens_stops_and_keeps_the_draft(self, setup: Setup) -> None:
        def failing_ready(number: int) -> None:
            raise ForgeError("gh failed")

        setup.forge.set_ready = failing_ready  # type: ignore[method-assign]

        result = setup.run()

        assert result.outcome == "stopped" and "gh failed" in result.detail
        assert result.pr_number == 42 and len(setup.sent) == 1

    def test_a_summary_with_a_mention_or_a_link_is_not_published(self, setup: Setup) -> None:
        setup.run(setup.agent(summary="Thanks @someone, see https://example.test"))

        assert setup.forge.bodies == []

    def test_a_mention_inside_code_is_published(self, setup: Setup) -> None:
        setup.run(setup.agent(summary="Added tests using `@pytest.mark.parametrize`."))

        assert len(setup.forge.bodies) == 1


class TestRerunAfterFailures:
    def test_a_failed_claim_puts_the_checkout_back_and_removes_the_local_branch(self, setup: Setup) -> None:
        setup.git.push_error = ForgeError("rejected")

        result = setup.run()

        assert setup.git.discarded == ["start000"] and setup.git.switched == ["develop"]
        assert setup.git.deleted == ["feature/thing"]
        assert "back on develop" in result.detail and "git push origin --delete feature/thing" in result.detail

    def test_a_cleanup_that_fails_says_what_to_remove_by_hand(self, setup: Setup) -> None:
        setup.git.push_error = ForgeError("rejected")
        setup.git.cleanup_error = ForgeError("branch is checked out")

        result = setup.run()

        assert "remove it by hand" in result.detail and "branch is checked out" in result.detail

    def test_a_question_is_recorded_and_nothing_is_pushed_when_a_guarded_path_was_touched(self, setup: Setup) -> None:
        setup.git.changed = ["src/infrastructure/brokers/ibkr.py"]

        result = setup.run(setup.agent(questions="Is the endpoint public?", summary="Changed the adapter."))

        assert result.outcome == "needs-owner" and "Is the endpoint public?" in result.detail
        assert "push" not in setup.git.calls and setup.git.forwarded == []
        assert "## Questions for the owner" in setup.forge.bodies[0][1]

    def test_guarded_commits_are_never_pushed_or_applied_but_are_kept_in_a_local_ref(self, setup: Setup) -> None:
        setup.git.changed = ["src/infrastructure/brokers/ibkr.py"]

        result = setup.run()

        assert result.outcome == "needs-owner" and setup.forge.ready == []
        assert "push" not in setup.git.calls and setup.git.forwarded == []
        assert len(setup.git.held) == 1 and setup.git.held[0][1] == "work111"
        assert "refs/forge/held/" in result.detail and "Nothing was pushed" in result.detail


class TestSandboxedPickup:
    def test_the_agent_works_in_a_sandbox_cut_from_the_claim_commit_and_it_is_closed(self, setup: Setup) -> None:
        setup.run()

        assert setup.sandboxes.refs[0] == "start000" and setup.sandboxes.closed == 2

    def test_the_gate_runs_in_a_second_clean_clone_of_the_pushed_commit_never_in_the_checkout(
        self, setup: Setup
    ) -> None:
        setup.run()

        assert setup.sandboxes.refs == ["start000", "work111"] and setup.sandboxes.installs == [True, False]
        assert setup.gate_runs == [setup.work / "box2"]

    def test_uncommitted_work_left_in_the_sandbox_keeps_the_pull_request_a_draft_and_skips_the_gate(
        self, setup: Setup
    ) -> None:
        setup.sandboxes.dirty = ["?? notes.txt"]

        result = setup.run()

        assert result.outcome == "needs-owner" and "notes.txt" in result.detail
        assert result.detail.startswith(
            "The agent left uncommitted changes in the sandbox, which were not pushed, so the pull request stays a draft: "
        )
        assert setup.gate_runs == [] and setup.forge.ready == []

    def test_the_commits_are_imported_relative_to_the_commit_the_sandbox_was_cut_from(self, setup: Setup) -> None:
        setup.run()

        assert setup.git.imported == [(setup.work / "box", "start000")]

    def test_the_agent_is_started_in_the_sandbox(self, setup: Setup) -> None:
        setup.run()

        assert setup.tasks[0].cwd == setup.work / "box"

    def test_an_agent_failure_closes_the_sandbox_and_never_touches_the_checkout(self, setup: Setup) -> None:
        result = setup.run(setup.agent(fail=True))

        assert result.outcome == "stopped" and setup.sandboxes.closed == 1
        assert setup.git.forwarded == [] and setup.git.discarded == []

    def test_commits_are_applied_to_the_checkout_and_pushed_only_from_the_fetched_copy(self, setup: Setup) -> None:
        setup.run()

        assert setup.git.forwarded == ["work111"] and setup.git.calls.count("push") == 1

    def test_commits_that_do_not_descend_from_the_claim_are_refused_and_the_run_stops(self, setup: Setup) -> None:
        setup.git.ff_error = ForgeError("not a fast-forward")

        result = setup.run()

        assert result.outcome == "stopped" and "not a fast-forward" in result.detail and setup.forge.ready == []


class TestPickupEdges:
    def test_a_detached_head_is_refused_before_any_branch_is_made(self, setup: Setup) -> None:
        setup.git.branch_name = ""

        result = setup.run()

        assert result.outcome == "refused" and "detached" in result.detail
        assert not any(call.startswith("branch") for call in setup.git.calls)

    def test_a_head_that_cannot_be_read_after_the_branch_is_made_is_a_refusal_not_a_crash(self, setup: Setup) -> None:
        setup.git.head_error = ForgeError("no head")

        result = setup.run()

        assert result.outcome == "refused" and "no head" in result.detail

    def test_a_withheld_summary_is_named_in_the_result(self, setup: Setup) -> None:
        result = setup.run(setup.agent(summary="key sk-ant-abcdefghij12345"))

        assert "withheld" in result.detail and setup.forge.bodies == []

    def test_a_published_summary_adds_no_withheld_sentence(self, setup: Setup) -> None:
        result = setup.run(setup.agent(summary="Added the thing."))

        assert "withheld" not in result.detail

    def test_guarded_paths_take_precedence_over_leftovers_and_the_gate_does_not_run(self, setup: Setup) -> None:
        setup.git.changed = ["src/infrastructure/brokers/ibkr.py"]
        setup.sandboxes.dirty = [" M notes.txt"]

        result = setup.run()

        assert result.outcome == "needs-owner" and "guarded" in result.detail and setup.gate_runs == []

    def test_questions_take_precedence_over_leftovers(self, setup: Setup) -> None:
        setup.sandboxes.dirty = [" M notes.txt"]

        result = setup.run(setup.agent(questions="Which one?"))

        assert result.detail.startswith("The agent has questions")


class TestPushTargets:
    def test_the_claim_and_the_agents_commits_are_pushed_to_the_plans_branch(self, setup: Setup) -> None:
        setup.run()

        assert setup.git.pushed_branches == ["feature/thing", "feature/thing"]

    def test_the_held_ref_in_the_result_names_the_commit(self, setup: Setup) -> None:
        setup.git.changed = ["src/infrastructure/brokers/ibkr.py"]

        result = setup.run()

        assert "refs/forge/held/feature/thing/work111" in result.detail


class TestCommandWiring:
    def _captured(self, monkeypatch: pytest.MonkeyPatch, setup: Setup, *flags: str) -> dict[str, object]:
        from scripts.forge import cli as cli_module

        seen: dict[str, object] = {}

        class Done:
            detail = ""
            fix = None

            class implement:  # noqa: N801
                outcome = "ready-for-review"
                plan = "thing.md"
                branch = "b"
                pr_url = None
                detail = ""
                pr_number = 1

        def fake(
            forge: object,
            git: object,
            implement_agent: object,
            fix_agent: object,
            sandbox_factory: object,
            gate: object,
            notify: object,
            repo_root: object,
            work_dir: object,
            plan_file: object,
            *_rest: object,
            **kwargs: object,
        ) -> object:
            seen.update(
                forge=forge,
                git=git,
                implement_agent=implement_agent,
                fix_agent=fix_agent,
                sandbox_factory=sandbox_factory,
                plan_file=plan_file,
            )
            seen.update(kwargs)
            seen["max_rounds"] = kwargs.get("max_rounds")
            return Done()

        monkeypatch.setattr(cli_module, "run_pipeline", fake)
        monkeypatch.setattr(cli_module, "LocalGit", lambda: setup.git)
        monkeypatch.setattr(cli_module, "_sandbox_factory", lambda git, install=True: setup.sandboxes)
        monkeypatch.setattr(cli_module, "asdict", lambda value: {})
        cli_module.main(["implement-plan", "--plan", "plan/thing.md", *flags], setup.forge)
        return seen

    def test_the_defaults_fix_the_pull_request_and_mark_it_ready(
        self, monkeypatch: pytest.MonkeyPatch, setup: Setup
    ) -> None:
        seen = self._captured(monkeypatch, setup)

        assert seen["forge"] is setup.forge and seen["git"] is setup.git and seen["sandbox_factory"] is setup.sandboxes
        assert seen["plan_file"] == "thing.md" and seen["implement_agent"] is seen["fix_agent"]
        assert seen["fix"] is True and seen["mark_ready"] is True and seen["depends_ok"] is False
        assert seen["base"] == "develop" and seen["max_rounds"] == 3

    def test_each_flag_reaches_the_pipeline(self, monkeypatch: pytest.MonkeyPatch, setup: Setup) -> None:
        seen = self._captured(
            monkeypatch,
            setup,
            "--no-fix",
            "--no-ready",
            "--depends-ok",
            "--base",
            "main",
            "--max-rounds",
            "2",
            "--review-wait-minutes",
            "5",
            "--wait-minutes",
            "7",
        )

        assert seen["fix"] is False and seen["mark_ready"] is False and seen["depends_ok"] is True
        assert seen["base"] == "main" and seen["max_rounds"] == 2
        assert seen["review_wait_seconds"] == 300 and seen["wait_seconds"] == 420


class TestHoldFailure:
    def test_a_hold_that_fails_still_reports_and_still_records_the_note(self, setup: Setup) -> None:
        setup.git.changed = ["src/infrastructure/brokers/ibkr.py"]

        def broken(name: str, sha: str) -> str:
            raise ForgeError("ref is locked")

        setup.git.hold = broken  # type: ignore[method-assign]

        result = setup.run(setup.agent(summary="Changed the adapter."))

        assert (
            result.outcome == "needs-owner"
            and "could not be kept" in result.detail
            and "ref is locked" in result.detail
        )
        assert setup.forge.bodies


class TestPickupReadsTheBase:
    def test_a_plan_index_missing_from_the_base_is_refused_before_any_branch_is_made(self, setup: Setup) -> None:
        del setup.git.files["plan/README.md"]

        result = setup.run()

        assert result.outcome == "refused" and "README.md" in result.detail
        assert not any(call.startswith("branch") for call in setup.git.calls)

    def test_a_failed_hold_names_the_commit_that_is_still_in_the_repository(self, setup: Setup) -> None:
        setup.git.changed = ["src/infrastructure/brokers/ibkr.py"]

        def broken(name: str, sha: str) -> str:
            raise ForgeError("ref is locked")

        setup.git.hold = broken  # type: ignore[method-assign]

        result = setup.run()

        assert "work111" in result.detail and "unreferenced" in result.detail and "lost" not in result.detail
        assert "git branch <name> work111" in result.detail and "ref is locked" in result.detail


class TestGateTiming:
    def test_the_gate_runs_while_its_own_sandbox_is_open_and_after_the_agents_closed(self, setup: Setup) -> None:
        setup.run()

        assert setup.closed_when_gated == [1]
        assert setup.sandboxes.closed == 2 and setup.gate_runs != [setup.work / "box"]
