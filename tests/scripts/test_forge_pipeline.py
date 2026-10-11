from collections.abc import Collection
from pathlib import Path

import pytest

from scripts.forge.base import Comment, ForgeError, PullRequest
from scripts.forge.pipeline import PipelineResult, run_pipeline
from tests.scripts.test_forge import FakeClock
from tests.scripts.test_forge_implement import FakeGit as PlanFakeGit, Setup
from tests.scripts.test_forge_loop import OPEN_CONCERN, comment_with, fixing_agent, readiness


class WorldGit(PlanFakeGit):
    """The plan-pickup fake plus what the fixer loop needs; a push can bring the next review pass."""

    def __init__(self) -> None:
        super().__init__()
        self.forge: object | None = None
        self.on_push: list[Comment] = []
        self.pushes = 0
        self.removals: list[str] = []
        self.dirty_after_pickup = False
        self._clean_checks = 0

    def push(self, branch: str = "") -> None:
        self.pushes += 1
        assert self.forge is not None
        self.forge.head_sha = self.head_value
        if self.on_push and self.forge.previous is not None:
            self.forge.previous = self.on_push.pop(0)

    def discard_changes(self, sha: str) -> None:
        self.head_value = sha

    def dirty_paths(self) -> list[str]:
        return []

    def remove_and_commit(self, remove: Collection[Path], update: Collection[Path], message: str) -> None:
        for path in remove:
            path.unlink()
        self.removals.append(message)
        self.head_value = "removed1"

    def require_clean_tree(self) -> None:
        self._clean_checks += 1
        if self.dirty_after_pickup and self._clean_checks > 1:
            raise ForgeError("The working tree has uncommitted changes.")


class World:
    def __init__(self, tmp_path: Path, first_review: Comment | None) -> None:
        self.setup = Setup(tmp_path)
        self.git = WorldGit()
        self.setup.git = self.git  # type: ignore[assignment]
        forge = self.setup.forge
        self.first_review = first_review
        self.sent = self.setup.sent
        git = self.git

        def pull_request(number: int | None) -> PullRequest:
            return PullRequest(
                number or 42, "https://example.test/pull/42", "develop", "feature/thing", git.head(), False, "OPEN"
            )

        def set_ready(number: int) -> None:
            forge.ready.append(number)
            forge.previous = self.first_review

        def upsert_comment(number: int, body: str, authors: Collection[str]) -> tuple[Comment, bool]:
            forge.previous = Comment(id=1, body=body, author="bot")
            forge.upserted.append(body)
            return forge.previous, False

        forge.pull_request = pull_request  # type: ignore[method-assign]
        forge.set_ready = set_ready  # type: ignore[method-assign]
        forge.upsert_comment = upsert_comment  # type: ignore[method-assign]
        self.git.forge = forge  # type: ignore[assignment]

    def run(self, fix_agent: object = None, **kwargs: object) -> PipelineResult:
        clock = FakeClock()
        implement_agent = self.setup.agent()
        return run_pipeline(
            self.setup.forge,
            self.git,  # type: ignore[arg-type]
            implement_agent,
            fix_agent or (lambda task: None),  # type: ignore[arg-type]
            lambda base: self.setup.gate_result,
            lambda subject, message, details: self.sent.append((subject, message, details)),
            self.setup.repo,
            self.setup.work,
            "thing.md",
            ["bot"],
            interval_seconds=10,
            review_wait_seconds=60,
            wait_seconds=100,
            sleep=clock.sleep,
            clock=clock,
            **kwargs,  # type: ignore[arg-type]
        )


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path, comment_with(readiness(1, concerns=OPEN_CONCERN)))


class TestPipeline:
    def test_a_ready_pull_request_goes_on_into_the_fixer_and_finishes_with_one_notification(
        self, world: World
    ) -> None:
        world.git.on_push = [comment_with(readiness(2, "READY")), comment_with(readiness(3, "READY"))]

        result = world.run(fixing_agent(world.git))

        assert result.implement.outcome == "ready-for-review"
        assert result.fix is not None and (result.fix.outcome, result.fix.rounds) == ("ready", 1)
        assert len(world.sent) == 1 and "READY" in world.sent[0][0]

    def test_the_claimed_plan_is_removed_when_the_fixer_reaches_ready(self, world: World) -> None:
        world.git.on_push = [comment_with(readiness(2, "READY")), comment_with(readiness(3, "READY"))]

        world.run(fixing_agent(world.git))

        assert not (world.setup.repo / "plan" / "thing.md").exists()
        assert "thing.md" not in (world.setup.repo / "plan" / "README.md").read_text(encoding="utf-8")
        assert len(world.git.removals) == 1

    def test_a_first_review_that_is_already_ready_needs_no_fixing_round(self, world: World) -> None:
        world.first_review = comment_with(readiness(1, "READY"))
        world.git.on_push = [comment_with(readiness(2, "READY"))]

        result = world.run()

        assert result.fix is not None and (result.fix.outcome, result.fix.rounds) == ("ready", 0)
        assert len(world.git.removals) == 1

    def test_no_fix_stops_after_the_pull_request_is_ready_and_notifies_once(self, world: World) -> None:
        result = world.run(fix=False)

        assert result.implement.outcome == "ready-for-review" and result.fix is None
        assert len(world.sent) == 1 and "ready-for-review" in world.sent[0][0]

    def test_a_pull_request_left_as_a_draft_is_not_fixed(self, world: World) -> None:
        result = world.run(mark_ready=False)

        assert result.fix is None and world.setup.forge.ready == []

    def test_a_pickup_that_needs_the_owner_does_not_start_the_fixer(self, world: World) -> None:
        world.setup.gate_result = (False, "FAIL")

        result = world.run()

        assert result.implement.outcome == "needs-owner" and result.fix is None
        assert len(world.sent) == 1

    def test_a_review_that_never_arrives_says_so_and_notifies_once(self, world: World) -> None:
        world.first_review = None

        result = world.run()

        assert result.fix is None and "first review did not arrive" in result.detail
        assert len(world.sent) == 1 and "fixer not started" in world.sent[0][0]

    def test_a_tree_that_became_dirty_stops_before_the_fixer(self, world: World) -> None:
        world.git.dirty_after_pickup = True

        result = world.run()

        assert result.fix is None and "did not start" in result.detail
        assert len(world.sent) == 1


class TestLoopAuthors:
    def _args(self, author: list[str]) -> object:
        import argparse

        return argparse.Namespace(author=author)

    def test_the_given_authors_win(self, tmp_path: Path) -> None:
        from scripts.forge.cli import _loop_authors

        assert _loop_authors(self._args(["someone"]), Setup(tmp_path).forge) == ["someone"]  # type: ignore[arg-type]

    def test_by_default_the_review_workflow_and_the_owner_are_trusted(self, tmp_path: Path) -> None:
        from scripts.forge.cli import _loop_authors

        assert _loop_authors(self._args([]), Setup(tmp_path).forge) == ["github-actions[bot]", "me"]  # type: ignore[arg-type]

    def test_without_a_known_owner_only_the_review_workflow_is_trusted(self, tmp_path: Path) -> None:
        from scripts.forge.cli import _loop_authors

        forge = Setup(tmp_path).forge
        forge.user = None

        assert _loop_authors(self._args([]), forge) == ["github-actions[bot]"]  # type: ignore[arg-type]
