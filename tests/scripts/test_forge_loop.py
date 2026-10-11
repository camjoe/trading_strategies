from pathlib import Path

import pytest

from scripts.forge.base import READINESS_MARKER, Comment
from scripts.forge.findings import open_counts, parse_findings, unhandled_open_findings, verdict
from scripts.forge.fix_loop import LoopResult, RoundTask, run_fix_loop
from scripts.forge.guarded_paths import guarded_paths_touched
from tests.scripts.test_forge import FakeClock, StubForge


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
        self.on_push: list[Comment] = []
        self.forge: "LoopForge | None" = None

    def head(self) -> str:
        return self.head_value

    def changed_paths(self, base: str, head: str) -> list[str]:
        return self.changed

    def reset_hard(self, sha: str) -> None:
        self.reset_to.append(sha)
        self.head_value = sha

    def push(self) -> None:
        self.pushes += 1
        assert self.forge is not None
        self.forge.head_sha = self.head_value
        if self.on_push:
            self.forge.previous = self.on_push.pop(0)


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
) -> tuple[LoopResult, list[tuple[str, str, dict[str, object]]]]:
    sent: list[tuple[str, str, dict[str, object]]] = []
    clock = FakeClock()
    result = run_fix_loop(
        forge,
        git,
        agent or (lambda task: None),  # type: ignore[arg-type]
        lambda subject, message, details: sent.append((subject, message, details)),
        tmp_path,
        7,
        ["bot"],
        max_rounds=max_rounds,
        wait_seconds=wait_seconds,
        interval_seconds=10,
        sleep=clock.sleep,
        clock=clock,
    )
    return result, sent


def fixing_agent(
    git: FakeGit, new_head: str = "def456", line: str = "  *Fix attempted: def456, awaiting verification*\n"
):
    def agent(task: RoundTask) -> None:
        git.head_value = new_head
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

    def test_a_round_that_touches_a_guarded_path_is_undone_and_nothing_is_posted(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))
        git.changed = [".github/workflows/pr-readiness.yml"]

        result, _ = run(forge, git, tmp_path, fixing_agent(git))

        assert result.outcome == "stopped" and "guarded" in result.detail
        assert git.reset_to == ["abc123"] and git.pushes == 0 and forge.upserted == []

    def test_a_body_that_edits_a_finding_is_refused_and_not_pushed(self, tmp_path: Path) -> None:
        forge, git = world(readiness(concerns=OPEN_CONCERN))

        def agent(task: RoundTask) -> None:
            git.head_value = "def456"
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
            git.head_value = next(heads)
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
        forge, git = world(readiness(title="READY", concerns=OPEN_CONCERN))

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
