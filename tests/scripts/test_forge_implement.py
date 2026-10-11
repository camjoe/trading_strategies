from collections.abc import Collection
from pathlib import Path

import pytest

from scripts.forge.base import ForgeError
from scripts.forge.implement import ImplementResult, ImplementTask, run_implement_plan
from tests.scripts.test_forge import StubForge

PLAN = "# Plan: add the thing\n\nStatus: drafted 2026-10-10. Not started.\n\n## Goal\nDo it.\n"
README = (
    "# plan/\n\n## Index\n| Plan | Status | Depends on |\n|---|---|---|\n"
    "| [thing.md](thing.md) | Drafted 2026-10-10. | none |\n"
    "| [later.md](later.md) | Drafted. | PR #9 merged |\n"
)


class FakeGit:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.head_value = "start000"
        self.changed: list[str] = []
        self.branch_error: ForgeError | None = None
        self.committed: list[tuple[list[str], str]] = []
        self.dirty: list[str] = []
        self.ignored: list[str] = []
        self.discarded: list[str] = []
        self.on_base = True
        self.switched: list[str] = []
        self.deleted: list[str] = []
        self.cleanup_error: ForgeError | None = None
        self.push_new_error: ForgeError | None = None

    def head(self) -> str:
        return self.head_value

    def changed_paths(self, base: str, head: str) -> list[str]:
        return self.changed

    def push(self, branch: str = "") -> None:
        self.calls.append("push")

    def require_clean_tree(self) -> None:
        self.calls.append("clean")

    def fetch(self) -> None:
        self.calls.append("fetch")

    def create_branch(self, name: str, start: str) -> None:
        if self.branch_error:
            raise self.branch_error
        self.calls.append(f"branch {name} {start}")

    def commit_files(self, paths: Collection[Path], message: str) -> None:
        self.calls.append("claim")
        self.committed.append(([path.name for path in paths], message))

    def push_new_branch(self, name: str) -> None:
        if self.push_new_error:
            raise self.push_new_error
        self.calls.append(f"push-new {name}")

    def dirty_paths(self) -> list[str]:
        return self.dirty

    def ignored_changes(self, since: float) -> list[str]:
        return self.ignored

    def discard_changes(self, sha: str) -> None:
        self.discarded.append(sha)
        self.dirty = []

    def exists_on(self, ref: str, relative: str) -> bool:
        return self.on_base

    def current_branch(self) -> str:
        return "develop"

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
        self.forge = StubForge()
        self.sent: list[tuple[str, str, dict[str, object]]] = []
        self.tasks: list[ImplementTask] = []
        self.gate_result = (True, "ok")

    def agent(self, commits: bool = True, questions: str = "", fail: bool = False, summary: str = ""):  # type: ignore[no-untyped-def]
        def run(task: ImplementTask) -> None:
            self.git.calls.append("agent")
            self.tasks.append(task)
            if fail:
                raise ForgeError("not logged in")
            if commits:
                self.git.head_value = "work111"
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
            lambda base: self.gate_result,
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
    def test_a_missing_plan_is_refused_before_git_is_touched(self, setup: Setup) -> None:
        result = setup.run(plan="nope.md")

        assert result.outcome == "refused" and setup.git.calls == []

    def test_a_plan_with_unconfirmed_dependencies_is_refused(self, setup: Setup) -> None:
        result = setup.run(plan="later.md")

        assert result.outcome == "refused" and "depends on" in result.detail
        assert setup.git.calls == [] and setup.forge.opened == []

    def test_confirming_the_dependencies_lets_it_through(self, setup: Setup) -> None:
        assert setup.run(plan="later.md", depends_ok=True).outcome == "ready-for-review"

    def test_a_plan_already_in_progress_is_refused(self, setup: Setup) -> None:
        path = setup.repo / "plan" / "thing.md"
        path.write_text(PLAN.replace("drafted", "in progress (branch `x`)"), encoding="utf-8")

        assert "Already in progress" in setup.run().detail

    def test_a_branch_that_cannot_be_created_is_refused_and_no_pull_request_opens(self, setup: Setup) -> None:
        setup.git.branch_error = ForgeError("branch exists")

        result = setup.run()

        assert result.outcome == "refused" and setup.forge.opened == []

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
            "push-new feature/thing",
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


class TestPrompt:
    def test_it_names_the_plan_branch_and_files_and_forbids_pushing(self, setup: Setup) -> None:
        setup.run()

        prompt = setup.tasks[0].prompt
        assert "plan/thing.md" in prompt and "feature/thing" in prompt
        assert str(setup.tasks[0].questions_file) in prompt and str(setup.tasks[0].summary_file) in prompt
        assert "Do not push" in prompt and "do not use gh" in prompt


class TestImplementPlanCommand:
    def test_a_refusal_exits_one_and_a_clean_run_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], setup: Setup
    ) -> None:
        from scripts.forge import cli as cli_module

        monkeypatch.setattr(cli_module, "get_repo_root", lambda: setup.repo)
        monkeypatch.setattr(cli_module, "LocalGit", lambda: setup.git)
        monkeypatch.setattr(cli_module, "run_claude_agent", lambda task, model=None: None)
        monkeypatch.setattr(cli_module, "run_gate", lambda base: (True, "ok"))
        monkeypatch.setattr(cli_module, "email_notifier", lambda subject, message, details: None)

        assert cli_module.main(["implement-plan", "--plan", "plan/nope.md"], setup.forge) == 1
        assert '"outcome": "refused"' in capsys.readouterr().out
        assert cli_module.main(["implement-plan", "--plan", "plan/thing.md", "--no-ready"], setup.forge) == 0
        assert '"outcome": "no-progress"' in capsys.readouterr().out


class TestPickupHardening:
    def test_a_plan_that_is_not_on_the_base_is_refused_before_any_branch_is_made(self, setup: Setup) -> None:
        setup.git.on_base = False

        result = setup.run()

        assert result.outcome == "refused" and "is not on origin/develop" in result.detail
        assert not any(call.startswith("branch") for call in setup.git.calls) and setup.forge.opened == []

    def test_a_failed_claim_push_stops_with_a_hint_to_delete_the_branch_and_still_notifies(self, setup: Setup) -> None:
        setup.git.push_new_error = ForgeError("rejected")

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

    def test_an_uncommitted_edit_to_a_guarded_path_keeps_it_a_draft_and_is_discarded(self, setup: Setup) -> None:
        setup.git.dirty = ["scripts/checks/repo/review_scope_check.py"]

        result = setup.run()

        assert result.outcome == "needs-owner" and "guarded" in result.detail and setup.forge.ready == []
        assert setup.git.discarded == ["work111"]

    def test_a_file_git_ignores_that_tools_run_keeps_it_a_draft(self, setup: Setup) -> None:
        setup.git.ignored = [".venv/Lib/site-packages/sitecustomize.py"]

        result = setup.run()

        assert result.outcome == "needs-owner" and "sitecustomize" in result.detail and setup.forge.ready == []

    def test_any_uncommitted_leftover_blocks_ready_and_is_discarded(self, setup: Setup) -> None:
        setup.git.dirty = ["notes.txt"]

        result = setup.run()

        assert result.outcome == "needs-owner" and "uncommitted" in result.detail and setup.forge.ready == []
        assert setup.git.discarded == ["work111"]

    def test_a_summary_with_a_mention_or_a_link_is_not_published(self, setup: Setup) -> None:
        setup.run(setup.agent(summary="Thanks @someone, see https://example.test"))

        assert setup.forge.bodies == []

    def test_a_mention_inside_code_is_published(self, setup: Setup) -> None:
        setup.run(setup.agent(summary="Added tests using `@pytest.mark.parametrize`."))

        assert len(setup.forge.bodies) == 1


class TestRerunAfterFailures:
    def test_a_failed_claim_puts_the_checkout_back_and_removes_the_local_branch(self, setup: Setup) -> None:
        setup.git.push_new_error = ForgeError("rejected")

        result = setup.run()

        assert setup.git.discarded == ["start000"] and setup.git.switched == ["develop"]
        assert setup.git.deleted == ["feature/thing"]
        assert "back on develop" in result.detail and "git push origin --delete feature/thing" in result.detail

    def test_a_cleanup_that_fails_says_what_to_remove_by_hand(self, setup: Setup) -> None:
        setup.git.push_new_error = ForgeError("rejected")
        setup.git.cleanup_error = ForgeError("branch is checked out")

        result = setup.run()

        assert "remove it by hand" in result.detail and "branch is checked out" in result.detail

    def test_an_agent_that_fails_restores_the_checkout_to_the_claim(self, setup: Setup) -> None:
        setup.git.dirty = ["half-written.py"]

        result = setup.run(setup.agent(fail=True))

        assert result.outcome == "stopped" and setup.git.discarded == ["start000"]

    def test_leftover_files_are_discarded_even_when_the_agent_asks_a_question(self, setup: Setup) -> None:
        setup.git.dirty = ["scratch.txt"]

        result = setup.run(setup.agent(questions="Which tickers?"))

        assert result.outcome == "needs-owner" and "Which tickers?" in result.detail
        assert setup.git.discarded == ["work111"]

    def test_a_question_is_recorded_and_commits_pushed_even_when_a_guarded_path_was_touched(
        self, setup: Setup
    ) -> None:
        setup.git.changed = ["src/infrastructure/brokers/ibkr.py"]

        result = setup.run(setup.agent(questions="Is the endpoint public?", summary="Changed the adapter."))

        assert result.outcome == "needs-owner" and "Is the endpoint public?" in result.detail
        assert "push" in setup.git.calls
        assert "## Questions for the owner" in setup.forge.bodies[0][1]

    def test_guarded_commits_are_pushed_to_the_draft_for_review_but_never_marked_ready(self, setup: Setup) -> None:
        setup.git.changed = ["src/infrastructure/brokers/ibkr.py"]

        result = setup.run()

        assert result.outcome == "needs-owner" and "push" in setup.git.calls and setup.forge.ready == []

    def test_a_changed_ignored_file_is_reported_as_not_restorable(self, setup: Setup) -> None:
        setup.git.ignored = [".claude/settings.local.json"]

        result = setup.run()

        assert result.outcome == "needs-owner" and "cannot be restored" in result.detail
