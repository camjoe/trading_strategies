import json
import sqlite3

import pytest

from scripts.forge import cli as cli_module
from scripts.forge.base import PullRequestDetails
from scripts.forge.scorecard import PullRequestScore, ScoredFinding, score_pull_request, tally
from scripts.forge.scorecard_store import SCHEMA_VERSION, ScoreStore, ScoreStoreError
from tests.scripts.test_forge_scorecard import BODY, ScoreStub


def score(*findings: ScoredFinding, passes: int | None = 3, verdict: str | None = "READY") -> PullRequestScore:
    return PullRequestScore(list(findings), passes, verdict)


FIXED = ScoredFinding(1, "fixed", ("Break it", "Operator"), "concern", up=2, down=0)
OPEN = ScoredFinding(2, "left open", ("Break it",), "note", up=0, down=1)


class TestStore:
    def test_a_saved_pull_request_comes_back_with_its_passes_verdict_and_finding_count(self, tmp_path) -> None:
        with ScoreStore(tmp_path / "s.db") as store:
            store.save("o/r", 7, score(FIXED, OPEN), "2026-10-17T12:00:00Z")

            [saved] = store.pull_requests()

        assert (saved.repo, saved.number, saved.passes, saved.verdict, saved.findings) == ("o/r", 7, 3, "READY", 2)
        assert saved.saved_at == "2026-10-17T12:00:00Z"

    def test_lens_totals_match_the_in_memory_tally(self, tmp_path) -> None:
        findings = [FIXED, OPEN]
        with ScoreStore(tmp_path / "s.db") as store:
            store.save("o/r", 7, score(*findings))

            assert store.lens_totals() == tally(findings)

    def test_saving_a_pull_request_again_replaces_its_rows(self, tmp_path) -> None:
        with ScoreStore(tmp_path / "s.db") as store:
            store.save("o/r", 7, score(FIXED, OPEN))
            store.save("o/r", 7, score(FIXED, passes=4))

            [saved] = store.pull_requests()
            totals = store.lens_totals()

        assert saved.findings == 1 and saved.passes == 4
        assert totals["Break it"]["findings"] == 1 and "left open" not in totals["Break it"]

    def test_one_file_holds_several_repos_and_can_be_filtered(self, tmp_path) -> None:
        with ScoreStore(tmp_path / "s.db") as store:
            store.save("o/a", 1, score(FIXED))
            store.save("o/b", 1, score(OPEN))

            assert store.lens_totals(["o/a"])["Break it"]["fixed"] == 1
            assert "fixed" not in store.lens_totals(["o/b"])["Break it"]
            assert [(pr.repo, pr.number) for pr in store.pull_requests()] == [("o/a", 1), ("o/b", 1)]
            assert [pr.repo for pr in store.pull_requests(["o/b"])] == ["o/b"]

    def test_the_data_survives_closing_and_reopening_the_file(self, tmp_path) -> None:
        with ScoreStore(tmp_path / "s.db") as store:
            store.save("o/r", 7, score(FIXED))

        with ScoreStore(tmp_path / "s.db") as store:
            assert store.lens_totals()["Operator"]["fixed"] == 1

    def test_the_parent_folder_is_created_and_the_schema_version_recorded(self, tmp_path) -> None:
        path = tmp_path / "local" / "s.db"

        with ScoreStore(path):
            pass

        assert sqlite3.connect(path).execute("SELECT version FROM schema_version").fetchone() == (SCHEMA_VERSION,)

    def test_a_file_from_another_schema_version_is_refused(self, tmp_path) -> None:
        path = tmp_path / "s.db"
        with ScoreStore(path):
            pass
        conn = sqlite3.connect(path)
        conn.execute("UPDATE schema_version SET version = 99")
        conn.commit()
        conn.close()

        with pytest.raises(ScoreStoreError, match="schema version 99"):
            ScoreStore(path)

    def test_a_pull_request_with_no_findings_is_still_recorded(self, tmp_path) -> None:
        with ScoreStore(tmp_path / "s.db") as store:
            store.save("o/r", 7, score(passes=1))

            assert [pr.findings for pr in store.pull_requests()] == [0]
            assert store.lens_totals() == {}

    def test_a_real_comment_round_trips_through_the_store(self, tmp_path) -> None:
        scored = score_pull_request(BODY)
        with ScoreStore(tmp_path / "s.db") as store:
            store.save("o/r", 20, scored)

            assert store.lens_totals() == tally(scored.findings)
            assert store.pull_requests()[0].passes == 3


class TestCli:
    def run(self, argv: list[str], stub: ScoreStub | None = None):
        return cli_module.main(["review-scorecard", *argv], forge=stub or ScoreStub({20: BODY, 10: BODY}))  # type: ignore[arg-type]

    def test_save_writes_each_scored_pull_request_under_the_repository_label(self, tmp_path, capsys) -> None:
        db = tmp_path / "s.db"

        code = self.run(["--pr", "20", "--pr", "10", "--save", "--db", str(db)])

        assert code == 0
        assert f"Saved to {db}." in capsys.readouterr().out
        with ScoreStore(db) as store:
            assert [(pr.repo, pr.number, pr.passes) for pr in store.pull_requests()] == [
                ("owner/repo", 10, 3),
                ("owner/repo", 20, 3),
            ]

    def test_a_repo_label_overrides_the_forge_name(self, tmp_path) -> None:
        db = tmp_path / "s.db"

        self.run(["--pr", "20", "--save", "--db", str(db), "--repo", "mine/other"])

        with ScoreStore(db) as store:
            assert [pr.repo for pr in store.pull_requests()] == ["mine/other"]

    def test_from_db_reports_without_calling_the_forge(self, tmp_path, capsys) -> None:
        db = tmp_path / "s.db"
        self.run(["--pr", "20", "--save", "--db", str(db)])
        capsys.readouterr()

        class NoForge:
            pass

        code = cli_module.main(["review-scorecard", "--from-db", "--db", str(db)], forge=NoForge())  # type: ignore[arg-type]

        out = capsys.readouterr().out
        assert code == 0
        assert out.startswith("6 findings from 1 saved pull request(s).")
        assert "Break it" in out

    def test_from_db_json_lists_the_saved_pull_requests_and_the_counts(self, tmp_path, capsys) -> None:
        db = tmp_path / "s.db"
        self.run(["--pr", "20", "--save", "--db", str(db)])
        capsys.readouterr()

        cli_module.main(["review-scorecard", "--from-db", "--db", str(db), "--json"], forge=object())  # type: ignore[arg-type]

        data = json.loads(capsys.readouterr().out)
        assert data["pull_requests"] == [{"repo": "owner/repo", "number": 20, "passes": 3}]
        assert data["lenses"]["Break it"]["findings"] == 4

    def test_from_db_refuses_to_mix_with_a_scoring_run(self, tmp_path, capsys) -> None:
        code = self.run(["--from-db", "--pr", "20", "--db", str(tmp_path / "s.db")])

        assert code == 1
        assert "reads the database only" in capsys.readouterr().err

    def test_the_database_path_can_come_from_the_environment(self, tmp_path, monkeypatch) -> None:
        db = tmp_path / "from_env.db"
        monkeypatch.setenv("REVIEW_SCORECARD_DB", str(db))

        self.run(["--pr", "20", "--save"])

        assert db.exists()

    def test_a_skipped_pull_request_is_not_saved(self, tmp_path) -> None:
        db = tmp_path / "s.db"

        self.run(["--pr", "99", "--pr", "20", "--save", "--db", str(db)])

        with ScoreStore(db) as store:
            assert [pr.number for pr in store.pull_requests()] == [20]


class TestMetadataRows:
    DETAILS = PullRequestDetails(
        title="A change",
        author="camjoe",
        base_ref="develop",
        head_ref="feature/x",
        created_at="2026-10-17T10:00:00Z",
        merged_at="2026-10-17T14:30:00Z",
        additions=30,
        deletions=4,
        commit_count=2,
        files=("src/a.py", "tests/test_a.py", "docs/a.md"),
    )

    def test_pull_request_details_and_file_areas_are_stored(self, tmp_path) -> None:
        scored = PullRequestScore(
            [FIXED],
            3,
            "READY",
            self.DETAILS,
            {"src/a.py": "code", "tests/test_a.py": "tests", "docs/a.md": "docs"},
        )
        with ScoreStore(tmp_path / "s.db") as store:
            store.save("o/r", 7, scored)

        conn = sqlite3.connect(tmp_path / "s.db")
        row = conn.execute(
            "SELECT title, author, base_ref, head_ref, created_at, merged_at, additions, deletions, commit_count "
            "FROM pull_request"
        ).fetchone()
        files = dict(conn.execute("SELECT path, area FROM pull_request_file").fetchall())
        assert row == (
            "A change",
            "camjoe",
            "develop",
            "feature/x",
            "2026-10-17T10:00:00Z",
            "2026-10-17T14:30:00Z",
            30,
            4,
            2,
        )
        assert files == {"src/a.py": "code", "tests/test_a.py": "tests", "docs/a.md": "docs"}

    def test_a_pull_request_saved_without_details_has_null_details_and_no_files(self, tmp_path) -> None:
        with ScoreStore(tmp_path / "s.db") as store:
            store.save("o/r", 7, score(FIXED))

        conn = sqlite3.connect(tmp_path / "s.db")
        assert conn.execute("SELECT title, author FROM pull_request").fetchone() == (None, None)
        assert conn.execute("SELECT COUNT(*) FROM pull_request_file").fetchone() == (0,)

    def test_saving_again_replaces_the_files_too(self, tmp_path) -> None:
        with ScoreStore(tmp_path / "s.db") as store:
            store.save("o/r", 7, PullRequestScore([FIXED], 3, "READY", self.DETAILS, {"src/a.py": "code"}))
            store.save("o/r", 7, PullRequestScore([FIXED], 4, "READY", None))

        assert sqlite3.connect(tmp_path / "s.db").execute("SELECT COUNT(*) FROM pull_request_file").fetchone() == (0,)

    def test_finding_metadata_is_stored(self, tmp_path) -> None:
        finding = ScoredFinding(
            1,
            "fixed",
            ("Break it",),
            "concern",
            1,
            0,
            "A title",
            "src/x.py",
            12,
            "code",
            "abc1234",
            "unconfirmed",
            "**1. A title.** body",
        )
        with ScoreStore(tmp_path / "s.db") as store:
            store.save("o/r", 7, score(finding))

        row = (
            sqlite3.connect(tmp_path / "s.db")
            .execute("SELECT title, path, line, area, fixed_in, lowered, text FROM finding")
            .fetchone()
        )
        assert row == ("A title", "src/x.py", 12, "code", "abc1234", "unconfirmed", "**1. A title.** body")

    def test_the_cli_save_stores_the_details_and_the_findings_metadata(self, tmp_path) -> None:
        db = tmp_path / "s.db"

        cli_module.main(["review-scorecard", "--pr", "20", "--save", "--db", str(db)], forge=ScoreStub({20: BODY}))  # type: ignore[arg-type]

        conn = sqlite3.connect(db)
        assert conn.execute("SELECT title, author, merged_at FROM pull_request").fetchone() == (
            "PR 20",
            "camjoe",
            "2026-10-17T14:30:00Z",
        )
        assert conn.execute("SELECT COUNT(*) FROM pull_request_file").fetchone() == (3,)
        assert conn.execute("SELECT fixed_in FROM finding WHERE number = 1").fetchone() == ("abc1234",)


class TestErrors:
    def run(self, argv: list[str], stub=None):
        return cli_module.main(["review-scorecard", *argv], forge=stub or ScoreStub({20: BODY}))  # type: ignore[arg-type]

    def test_a_database_of_another_version_is_a_forge_error_that_names_the_fix(self, tmp_path, capsys) -> None:
        db = tmp_path / "s.db"
        with ScoreStore(db):
            pass
        conn = sqlite3.connect(db)
        conn.execute("UPDATE schema_version SET version = 1")
        conn.commit()
        conn.close()

        code = self.run(["--pr", "20", "--save", "--db", str(db)])

        err = capsys.readouterr().err
        assert code == 1
        assert err.startswith("forge: ") and "schema version 1" in err and "Move or delete the file" in err

    def test_a_bad_database_is_found_before_any_pull_request_is_scored(self, tmp_path) -> None:
        db = tmp_path / "s.db"
        db.write_text("this is not a database", encoding="utf-8")

        class Counting(ScoreStub):
            calls = 0

            def find_comment(self, number, authors):
                Counting.calls += 1
                return super().find_comment(number, authors)

        code = self.run(["--pr", "20", "--save", "--db", str(db)], Counting({20: BODY}))

        assert code == 1 and Counting.calls == 0

    def test_a_corrupt_file_is_also_a_forge_error(self, tmp_path, capsys) -> None:
        db = tmp_path / "s.db"
        db.write_text("this is not a database", encoding="utf-8")

        code = self.run(["--from-db", "--db", str(db)])

        assert code == 1 and capsys.readouterr().err.startswith("forge: ")

    def test_from_db_on_a_missing_file_says_so_and_creates_nothing(self, tmp_path, capsys) -> None:
        db = tmp_path / "missing" / "s.db"

        code = self.run(["--from-db", "--db", str(db)])

        assert code == 1
        assert "No scorecard database" in capsys.readouterr().err
        assert not db.exists() and not db.parent.exists()

    def test_save_refuses_more_than_one_repo_label(self, tmp_path, capsys) -> None:
        code = self.run(["--pr", "20", "--save", "--db", str(tmp_path / "s.db"), "--repo", "a/b", "--repo", "c/d"])

        assert code == 1 and "at most once" in capsys.readouterr().err

    def test_save_with_json_reports_where_it_saved(self, tmp_path, capsys) -> None:
        db = tmp_path / "s.db"

        self.run(["--pr", "20", "--save", "--json", "--db", str(db)])

        assert json.loads(capsys.readouterr().out)["saved_to"] == str(db)

    def test_a_comment_that_repeats_a_finding_number_still_saves(self, tmp_path) -> None:
        repeated = ScoredFinding(1, "left open", ("Operator",), "note")
        with ScoreStore(tmp_path / "s.db") as store:
            store.save("o/r", 7, score(FIXED, repeated))

            assert [pr.findings for pr in store.pull_requests()] == [1]
            assert store.lens_totals() == tally([repeated])


class TestScoring:
    def test_file_areas_come_from_the_score_not_from_the_store(self) -> None:
        details = TestMetadataRows.DETAILS

        scored = score_pull_request(BODY, None, details)

        assert scored.file_areas == {"src/a.py": "code", "tests/test_a.py": "tests", "docs/a.md": "docs"}

    def test_a_txt_file_is_not_a_doc(self) -> None:
        from scripts.forge.scorecard import area_of

        assert area_of("requirements.txt") == "code"
