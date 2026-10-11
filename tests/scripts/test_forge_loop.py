from pathlib import Path

import pytest

from scripts.forge.base import READINESS_MARKER, Comment, ForgeError
from scripts.forge.findings import open_counts, parse_findings, unhandled_open_findings, verdict
from scripts.forge.fix_loop import LoopResult, RoundTask, run_fix_loop
from scripts.forge.guarded_paths import guarded_paths_touched
from tests.scripts.test_forge import FakeClock, FakeSandboxes, StubForge


def readiness(
    pass_no: int = 1, title: str = "NOT READY", concerns: str = "", notes: str = "", closed: str = ""
) -> str:
    return (
        f"{READINESS_MARKER}\n## PR readiness: {title}\n\n"
        f"Reviewed `abc` · 2026-10-10 · pass {pass_no} · current\n\n### Findings\n"
        f"#### 🟠 Concerns\n{concerns}\n#### 🟡 Notes\n{notes}\n#### Closed\n{closed}\n"
    )


OPEN_CONCERN = "- [ ] **1. A defect.**\n\n  Text.\n\n  *Pointer: fix it.*\n"
OPEN_NOTE = "- [ ] **2. A nit.** Text. *Caught by: Break it*\n"
HANDLED_NOTE = "- [ ] **3. Skipped.** Text.\n\n  *Left: style only*\n"
DECIDED_NOTE = "- [ ] **4. Decided.** Text.\n\n  *Decision: accepted by the owner*\n"
CLOSED = "- [x] **9. Done.** Fixed in `abc`.\n"


class TestParsing:
    def test_reads_the_verdict(self) -> None:
        assert verdict(readiness(title="READY")) == "READY"
        assert verdict(readiness()) == "NOT READY"
        assert verdict("no title") is None

    def test_tiers_checked_state_and_status_lines(self) -> None:
        body = readiness(concerns=OPEN_CONCERN, notes=HANDLED_NOTE + DECIDED_NOTE, closed=CLOSED)

        found = {finding.number: finding for finding in parse_findings(body)}

        assert found[1].tier == "concern"
        assert found[3].tier == "note"
        assert found[3].has_status_line and found[3].is_handled
        assert found[4].decided and found[4].is_handled
        assert found[9].tier == "closed" and found[9].checked
        assert not found[1].is_handled

    def test_unhandled_open_findings_are_the_ones_a_fixer_can_still_work(self) -> None:
        body = readiness(concerns=OPEN_CONCERN, notes=OPEN_NOTE + HANDLED_NOTE + DECIDED_NOTE, closed=CLOSED)

        assert [finding.number for finding in unhandled_open_findings(body)] == [1, 2]

    def test_counts_only_open_findings_per_tier(self) -> None:
        body = readiness(concerns=OPEN_CONCERN, notes=OPEN_NOTE + HANDLED_NOTE, closed=CLOSED)

        assert open_counts(body) == {"blocker": 0, "concern": 1, "note": 2}


class TestGuardedPaths:
    @pytest.mark.parametrize(
        "path",
        [
            "src/infrastructure/brokers/ibkr.py",
            "src/trading/services/execution/orders.py",
            "src/trading/domain/risk_gate.py",
            "src/infrastructure/database/migrate.py",
            ".github/workflows/pr-readiness.yml",
            ".ai/skills/fix-pr-readiness/SKILL.md",
            "AGENTS.md",
            "docs/adr/012-x.md",
            ".env.example",
            "scripts/forge/readiness.py",
            "local/strategies/private.md",
            "scripts\\forge\\cli.py",
        ],
    )
    def test_guarded_paths_are_reported_with_a_reason(self, path: str) -> None:
        assert [entry.split(":")[0] for entry in guarded_paths_touched([path])] == [path]

    @pytest.mark.parametrize(
        "path", ["src/common/tickers.py", "tests/scripts/test_forge.py", "docs/maps/scripts-map.md"]
    )
    def test_ordinary_paths_are_not_guarded(self, path: str) -> None:
        assert guarded_paths_touched([path]) == []


class FakeGit:
    def __init__(self, head: str = "abc123") -> None:
        self.head_value = head
        self.changed: list[str] = []
        self.reset_to: list[str] = []
        self.pushes = 0
        self.removals: list[str] = []
        self.sandbox_head: str | None = None
        self.imported: list[tuple[Path, str]] = []
        self.forwarded: list[str] = []
        self.ff_error: ForgeError | None = None
        self.push_error: ForgeError | None = None
        self.pushed_to: list[str] = []
        self.posted_before_push = -1
        self.changed_args: list[tuple[str, str]] = []
        self.on_push: list[Comment] = []
        self.forge: "LoopForge | None" = None

    def head(self) -> str:
        return self.head_value

    def changed_paths(self, base: str, head: str) -> list[str]:
        self.changed_args.append((base, head))
        return self.changed

    def discard_changes(self, sha: str) -> None:
        self.reset_to.append(sha)
        self.head_value = sha

    def import_commits(self, source: Path, since: str) -> str:
        self.imported.append((source, since))
        head, self.sandbox_head = self.sandbox_head or self.head_value, None
        return head

    def fast_forward(self, sha: str) -> None:
        if self.ff_error:
            raise self.ff_error
        self.forwarded.append(sha)
        self.head_value = sha

    def push(self, branch: str = "") -> None:
        if self.push_error:
            raise self.push_error
        self.pushes += 1
        self.pushed_to.append(branch)
        assert self.forge is not None
        self.posted_before_push = len(self.forge.upserted)
        self.forge.head_sha = self.head_value
        if self.on_push:
            self.forge.previous = self.on_push.pop(0)

    def remove_and_commit(self, remove: object, update: object, message: str) -> None:
        for path in remove:  # type: ignore[attr-defined]
            path.unlink()
        self.removals.append(message)
        self.head_value = "removed1"


class LoopForge(StubForge):
    def upsert_comment(self, number: int, body: str, authors: object) -> tuple[Comment, bool]:
        self.previous = Comment(id=1, body=body, author="bot")
        return super().upsert_comment(number, body, authors)  # type: ignore[arg-type]


def comment_with(body: str) -> Comment:
    return Comment(id=1, body=body, author="bot")


def world(body: str | None, next_bodies: tuple[str, ...] = ()) -> tuple[LoopForge, FakeGit]:
    forge = LoopForge(previous=None if body is None else comment_with(body))
    git = FakeGit()
    git.forge = forge
    git.on_push = [comment_with(next_body) for next_body in next_bodies]
    return forge, git


def run(
    forge: LoopForge,
    git: FakeGit,
    tmp_path: Path,
    agent: object = None,
    max_rounds: int = 3,
    wait_seconds: float = 100,
    repo_root: Path | None = None,
    sandboxes: FakeSandboxes | None = None,
) -> tuple[LoopResult, list[tuple[str, str, dict[str, object]]]]:
    sent: list[tuple[str, str, dict[str, object]]] = []
    clock = FakeClock()
    result = run_fix_loop(
        forge,
        git,
        agent or (lambda task: None),  # type: ignore[arg-type]
        sandboxes or FakeSandboxes(tmp_path),
        lambda subject, message, details: sent.append((subject, message, details)),
        tmp_path,
        7,
        ["bot"],
        max_rounds=max_rounds,
        wait_seconds=wait_seconds,
        interval_seconds=10,
        repo_root=repo_root,
        sleep=clock.sleep,
        clock=clock,
    )
    return result, sent


def fixing_agent(
    git: FakeGit, new_head: str = "def456", line: str = "  *Fix attempted: def456, awaiting verification*\n"
):
    def agent(task: RoundTask) -> None:
        git.sandbox_head = new_head
        old = task.old_comment_file.read_text(encoding="utf-8")
        task.new_comment_file.write_text(
            old.replace("  *Pointer: fix it.*\n", "  *Pointer: fix it.*\n\n" + line), encoding="utf-8"
        )

    return agent


class TestLoop:
    def test_a_ready_comment_stops_at_once_and_notifies(self, tmp_path: Path) -> None:
        forge, git = world(readiness(title="READY", notes=OPEN_NOTE))

        result, sent = run(forge, git, tmp_path)

        assert (result.outcome, result.rounds) == ("ready", 0)
        assert len(sent) == 1
        assert sent[0][2]["url"] == "u" and sent[0][2]["note"] == 1

    def test_no_comment_stops(self, tmp_path: Path) -> None:
        forge, git = world(None)

        assert run(forge, git, tmp_path)[0].outcome == "stopped"

    def test_a_local_head_that_is_not_the_pull_request_head_stops(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))
        git.head_value = "other"

        result, _ = run(forge, git, tmp_path)

        assert result.outcome == "stopped" and "newer push" in result.detail

    def test_when_every_open_finding_is_handled_the_owner_is_told(self, tmp_path: Path) -> None:
        forge, git = world(readiness(notes=HANDLED_NOTE + DECIDED_NOTE))

        assert run(forge, git, tmp_path)[0].outcome == "needs-owner"

    def test_a_round_that_fixes_and_pushes_then_waits_for_ready(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN), next_bodies=(readiness(2, "READY", closed=CLOSED),))

        result, sent = run(forge, git, tmp_path, fixing_agent(git))

        assert (result.outcome, result.rounds, git.pushes) == ("ready", 1, 1)
        assert len(sent) == 1

    def test_a_round_that_touches_a_guarded_path_is_discarded_and_nothing_reaches_the_checkout(
        self, tmp_path: Path
    ) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))
        git.changed = [".github/workflows/pr-readiness.yml"]

        result, _ = run(forge, git, tmp_path, fixing_agent(git))

        assert result.outcome == "stopped" and "guarded" in result.detail
        assert git.forwarded == [] and git.reset_to == [] and git.pushes == 0 and forge.upserted == []

    def test_a_body_that_edits_a_finding_is_refused_and_not_pushed(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))

        def agent(task: RoundTask) -> None:
            git.sandbox_head = "def456"
            old = task.old_comment_file.read_text(encoding="utf-8")
            task.new_comment_file.write_text(old.replace("A defect", "Fine"), encoding="utf-8")

        result, _ = run(forge, git, tmp_path, agent)

        assert result.outcome == "stopped" and "refused" in result.detail
        assert git.pushes == 0 and forge.upserted == []

    def test_a_round_with_no_body_is_no_progress(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))

        assert run(forge, git, tmp_path)[0].outcome == "no-progress"

    def test_status_lines_without_commits_are_posted_but_not_pushed(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))

        def agent(task: RoundTask) -> None:
            old = task.old_comment_file.read_text(encoding="utf-8")
            line = "  *Not fixed: needs a decision*\n"
            task.new_comment_file.write_text(
                old.replace("  *Pointer: fix it.*\n", "  *Pointer: fix it.*\n\n" + line), encoding="utf-8"
            )

        result, _ = run(forge, git, tmp_path, agent)

        assert result.outcome == "no-progress" and git.pushes == 0 and len(forge.upserted) == 1

    def test_the_loop_stops_at_the_round_cap(self, tmp_path: Path) -> None:
        bodies = tuple(readiness(n, concerns=OPEN_CONCERN) for n in (2, 3, 4))
        forge, git = world(readiness(concerns=OPEN_CONCERN), next_bodies=bodies)
        heads = iter(["h1", "h2", "h3", "h4"])

        def agent(task: RoundTask) -> None:
            git.sandbox_head = next(heads)
            old = task.old_comment_file.read_text(encoding="utf-8")
            line = "  *Fix attempted: x, awaiting verification*\n"
            task.new_comment_file.write_text(
                old.replace("  *Pointer: fix it.*\n", "  *Pointer: fix it.*\n\n" + line), encoding="utf-8"
            )

        result, _ = run(forge, git, tmp_path, agent, max_rounds=3)

        assert (result.outcome, result.rounds, git.pushes) == ("round-cap", 3, 3)

    def test_a_next_pass_that_never_arrives_stops_the_loop(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))

        result, _ = run(forge, git, tmp_path, fixing_agent(git), wait_seconds=25)

        assert result.outcome == "stopped" and "did not arrive" in result.detail

    def test_the_notification_carries_the_link_verdict_and_counts_only(self, tmp_path: Path) -> None:
        forge, git = world(readiness(title="READY", notes=OPEN_NOTE))

        _, sent = run(forge, git, tmp_path)

        subject, message, details = sent[0]
        assert "PR 7" in subject and "READY" in subject
        assert set(details) == {"url", "verdict", "outcome", "rounds", "blocker", "concern", "note"}
        assert "A defect" not in message


class TestFixLoopCommand:
    def _patch(self, monkeypatch: pytest.MonkeyPatch, git: FakeGit) -> None:
        from scripts.forge import cli as cli_module

        git.require_clean_tree = lambda: None  # type: ignore[attr-defined]
        monkeypatch.setattr(cli_module, "LocalGit", lambda: git)
        monkeypatch.setattr(cli_module, "_sandbox_factory", lambda local: FakeSandboxes(Path(".")))
        monkeypatch.setattr(cli_module, "run_claude_agent", lambda task, model=None: None)
        monkeypatch.setattr(cli_module, "email_notifier", lambda subject, message, details: None)

    def test_a_ready_pull_request_prints_the_result_and_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from scripts.forge.cli import main

        forge, git = world(readiness(title="READY"))
        self._patch(monkeypatch, git)

        assert main(["fix-loop", "--pr", "7", "--author", "bot"], forge) == 0
        assert '"outcome": "ready"' in capsys.readouterr().out

    def test_a_stopped_loop_exits_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from scripts.forge.cli import main

        forge, git = world(None)
        self._patch(monkeypatch, git)

        assert main(["fix-loop", "--pr", "7", "--author", "bot"], forge) == 1
        assert "no readiness comment" in capsys.readouterr().err.lower()


CLAIMED = "# Plan: x\n\nStatus: in progress (branch `feature/x`). Before pickup: drafted.\n"
INDEX = (
    "# plan/\n\n## Index\n| Plan | Status | Depends on |\n|---|---|---|\n"
    "| [x.md](x.md) | In progress (branch `feature/x`). | none |\n"
    "| [other.md](other.md) | Drafted. | none |\n"
)


class TestPlanFileRemoval:
    def _repo(self, tmp_path: Path, claimed_by: str = "feature/x") -> Path:
        root = tmp_path / "repo"
        (root / "plan").mkdir(parents=True)
        (tmp_path / "work").mkdir(exist_ok=True)
        (root / "plan" / "x.md").write_text(CLAIMED.replace("feature/x", claimed_by), encoding="utf-8")
        (root / "plan" / "other.md").write_text("# Plan: other\n\nStatus: drafted.\n", encoding="utf-8")
        (root / "plan" / "README.md").write_text(INDEX, encoding="utf-8")
        return root

    def test_at_ready_the_claimed_plan_and_its_index_row_are_removed_then_the_confirming_pass_is_awaited(
        self, tmp_path: Path
    ) -> None:
        root = self._repo(tmp_path)
        forge, git = world(readiness(title="READY"), next_bodies=(readiness(2, "READY"),))

        result, sent = run(forge, git, tmp_path / "work", repo_root=root)

        assert (result.outcome, git.pushes, len(git.removals)) == ("ready", 1, 1)
        assert "x.md" in git.removals[0] and not (root / "plan" / "x.md").exists()
        readme = (root / "plan" / "README.md").read_text(encoding="utf-8")
        assert "x.md" not in readme and "other.md" in readme
        assert (root / "plan" / "other.md").exists()
        assert len(sent) == 1

    def test_without_a_repo_root_nothing_is_removed(self, tmp_path: Path) -> None:
        self._repo(tmp_path)
        forge, git = world(readiness(title="READY"))

        result, _ = run(forge, git, tmp_path / "work")

        assert result.outcome == "ready" and git.removals == [] and git.pushes == 0

    def test_a_plan_claimed_by_another_branch_is_left_alone(self, tmp_path: Path) -> None:
        root = self._repo(tmp_path, claimed_by="feature/someone-else")
        forge, git = world(readiness(title="READY"))

        result, _ = run(forge, git, tmp_path / "work", repo_root=root)

        assert result.outcome == "ready" and git.removals == [] and (root / "plan" / "x.md").exists()

    def test_a_branch_with_no_claimed_plan_finishes_at_once(self, tmp_path: Path) -> None:
        root = self._repo(tmp_path)
        (root / "plan" / "x.md").write_text("# Plan: x\n\nStatus: drafted.\n", encoding="utf-8")
        forge, git = world(readiness(title="READY"))

        assert run(forge, git, tmp_path / "work", repo_root=root)[0].outcome == "ready"
        assert git.removals == []

    def test_a_confirming_pass_that_is_not_ready_sends_the_loop_back_to_fixing(self, tmp_path: Path) -> None:
        root = self._repo(tmp_path)
        forge, git = world(
            readiness(title="READY"),
            next_bodies=(readiness(2, concerns=OPEN_CONCERN), readiness(3, "READY")),
        )

        result, _ = run(forge, git, tmp_path / "work", fixing_agent(git), repo_root=root)

        assert (result.outcome, result.rounds, len(git.removals)) == ("ready", 1, 1)

    def test_a_confirming_pass_that_never_arrives_stops_the_loop(self, tmp_path: Path) -> None:
        root = self._repo(tmp_path)
        forge, git = world(readiness(title="READY"))

        result, _ = run(forge, git, tmp_path / "work", repo_root=root, wait_seconds=25)

        assert result.outcome == "stopped" and "confirming pass" in result.detail


class TestRoundHardening:
    def test_the_status_lines_are_posted_before_the_push_so_the_next_pass_reads_them(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN), next_bodies=(readiness(2, "READY"),))

        run(forge, git, tmp_path, fixing_agent(git))

        assert git.posted_before_push == 1 and "Fix attempted" in forge.upserted[0]

    def test_the_committed_paths_are_read_from_the_round_start_to_its_end(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN), next_bodies=(readiness(2, "READY"),))

        run(forge, git, tmp_path, fixing_agent(git, new_head="def456"))

        assert git.changed_args == [("abc123", "def456")]

    def test_the_push_goes_to_the_pull_requests_head_branch_by_name(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN), next_bodies=(readiness(2, "READY"),))

        run(forge, git, tmp_path, fixing_agent(git))

        assert git.pushed_to == ["feature/x"]

    def test_a_refused_body_drops_the_rounds_local_commits(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))

        def agent(task: RoundTask) -> None:
            git.sandbox_head = "def456"
            old = task.old_comment_file.read_text(encoding="utf-8")
            task.new_comment_file.write_text(old.replace("A defect", "Fine"), encoding="utf-8")

        result, _ = run(forge, git, tmp_path, agent)

        assert result.outcome == "stopped" and git.forwarded == [] and git.reset_to == []

    def test_a_round_with_commits_but_no_body_drops_them(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))

        def agent(task: RoundTask) -> None:
            git.sandbox_head = "def456"

        result, _ = run(forge, git, tmp_path, agent)

        assert result.outcome == "no-progress" and git.forwarded == [] and git.reset_to == []

    def test_a_failed_push_restores_the_comment_undoes_the_round_and_still_notifies(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))
        git.push_error = ForgeError("rejected")

        result, sent = run(forge, git, tmp_path, fixing_agent(git))

        assert result.outcome == "stopped" and "push failed" in result.detail
        assert len(forge.upserted) == 2 and forge.upserted[1].count("Fix attempted") == 0
        assert git.reset_to == ["abc123"] and len(sent) == 1

    def test_an_agent_that_fails_still_ends_with_a_result_and_a_notification(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))

        def agent(task: RoundTask) -> None:
            raise ForgeError("not logged in")

        result, sent = run(forge, git, tmp_path, agent)

        assert result.outcome == "stopped" and "not logged in" in result.detail
        assert len(sent) == 1

    def test_a_ready_title_with_open_concerns_is_not_ready(self, tmp_path: Path) -> None:
        forge, git = world(readiness(title="READY", concerns=OPEN_CONCERN))

        result, _ = run(forge, git, tmp_path)

        assert result.outcome != "ready"


class TestFindingsParsing:
    def test_the_blockers_tier_is_read(self) -> None:
        body = "#### 🔴 Blockers\n- [ ] **1. Bad.** Text.\n#### 🟡 Notes\n- [ ] **2. Nit.** Text.\n"

        assert open_counts(body) == {"blocker": 1, "concern": 0, "note": 1}

    def test_an_unchecked_item_under_closed_is_not_open(self) -> None:
        assert open_counts("#### Closed\n- [ ] **1. Odd.** Text.\n") == {"blocker": 0, "concern": 0, "note": 0}

    def test_a_heading_that_is_not_a_tier_ends_the_tier(self) -> None:
        body = "#### 🟡 Notes\n- [ ] **1. Nit.** Text.\n### How to verify\n- [ ] **2. Step.** Text.\n"

        assert open_counts(body) == {"blocker": 0, "concern": 0, "note": 1}

    def test_a_heading_that_only_mentions_a_tier_word_is_not_that_tier(self) -> None:
        assert open_counts("#### Notes on blockers\n- [ ] **1. X.** Text.\n") == {
            "blocker": 0,
            "concern": 0,
            "note": 0,
        }


class TestFindingsParsingContinuations:
    def test_a_continuation_line_that_starts_with_a_hash_does_not_end_the_tier(self) -> None:
        body = "#### Notes\n- [ ] **1. Nit.** See issue\n#123 for context.\n- [ ] **2. Other.** Text.\n"

        assert open_counts(body) == {"blocker": 0, "concern": 0, "note": 2}


class TestLoopHardeningTwo:
    def test_a_push_failure_is_reported_even_when_the_comment_cannot_be_restored(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))
        git.push_error = ForgeError("rejected")
        original = forge.upsert_comment
        calls: list[str] = []

        def upsert(number: int, body: str, authors: object) -> tuple[Comment, bool]:
            calls.append(body)
            if len(calls) > 1:
                raise ForgeError("api down")
            return original(number, body, authors)  # type: ignore[arg-type]

        forge.upsert_comment = upsert  # type: ignore[method-assign]

        result, sent = run(forge, git, tmp_path, fixing_agent(git))

        assert result.outcome == "stopped" and "could not be restored" in result.detail
        assert git.reset_to == ["abc123"] and len(sent) == 1


def test_an_agent_that_crashes_mid_round_never_touches_the_checkout(tmp_path: Path) -> None:
    forge, git = world(readiness(concerns=OPEN_CONCERN))

    def agent(task: RoundTask) -> None:
        git.sandbox_head = "def456"
        raise ForgeError("timed out")

    result, _ = run(forge, git, tmp_path, agent)

    assert result.outcome == "stopped" and "timed out" in result.detail
    assert git.forwarded == [] and git.reset_to == []


class TestSandboxedRound:
    def test_each_round_works_in_a_sandbox_cut_from_the_pull_requests_head_and_closes_it(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN), next_bodies=(readiness(2, "READY"),))
        boxes = FakeSandboxes(tmp_path)

        run(forge, git, tmp_path, fixing_agent(git), sandboxes=boxes)

        assert boxes.refs == ["abc123"] and boxes.closed == 1

    def test_the_agent_is_started_in_the_sandbox(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))
        seen: list[Path] = []

        def agent(task: RoundTask) -> None:
            seen.append(task.cwd)

        run(forge, git, tmp_path, agent)

        assert seen == [tmp_path / "box"]

    def test_the_sandbox_is_closed_even_when_the_agent_fails(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))
        boxes = FakeSandboxes(tmp_path)

        def agent(task: RoundTask) -> None:
            raise ForgeError("timed out")

        run(forge, git, tmp_path, agent, sandboxes=boxes)

        assert boxes.closed == 1

    def test_commits_are_applied_to_the_checkout_only_after_the_checks_pass(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN), next_bodies=(readiness(2, "READY"),))

        run(forge, git, tmp_path, fixing_agent(git, new_head="def456"))

        assert git.forwarded == ["def456"]

    def test_commits_that_do_not_descend_from_the_round_start_are_refused_and_nothing_is_posted(
        self, tmp_path: Path
    ) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))
        git.ff_error = ForgeError("not a fast-forward")

        result, sent = run(forge, git, tmp_path, fixing_agent(git))

        assert result.outcome == "stopped" and "not a fast-forward" in result.detail
        assert forge.upserted == [] and git.pushes == 0 and len(sent) == 1


class TestLeftovers:
    def test_uncommitted_changes_in_the_sandbox_discard_the_round_and_post_nothing(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))
        boxes = FakeSandboxes(tmp_path)
        boxes.dirty = [" M src/thing.py"]

        result, sent = run(forge, git, tmp_path, fixing_agent(git), sandboxes=boxes)

        assert result.outcome == "stopped" and "uncommitted" in result.detail and "src/thing.py" in result.detail
        assert git.forwarded == [] and forge.upserted == [] and git.pushes == 0 and len(sent) == 1

    def test_a_comment_that_cannot_be_posted_puts_the_branch_back(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))

        def refuse(number: int, body: str, authors: object) -> tuple[Comment, bool]:
            raise ForgeError("rate limited")

        forge.upsert_comment = refuse  # type: ignore[method-assign]

        result, _ = run(forge, git, tmp_path, fixing_agent(git))

        assert result.outcome == "stopped" and "rate limited" in result.detail
        assert git.forwarded == ["def456"] and git.reset_to == ["abc123"] and git.pushes == 0

    def test_the_commits_are_imported_relative_to_the_round_start(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN), next_bodies=(readiness(2, "READY"),))

        run(forge, git, tmp_path, fixing_agent(git))

        assert git.imported == [(tmp_path / "box", "abc123")]


def test_the_round_prompt_tells_the_fixer_to_leave_no_uncommitted_files() -> None:
    from scripts.forge.fix_loop import round_prompt

    assert "uncommitted" in round_prompt(7, "origin/develop", Path("old.md"), Path("new.md"))
