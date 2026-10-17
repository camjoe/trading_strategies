"""A small SQLite store for scored review findings.

Standard library only, and it knows nothing about a forge or a project: rows are keyed by a ``repo`` label, so
one file can hold the reviews of several projects.
"""

import sqlite3
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType

from scripts.forge.scorecard import PullRequestScore

SCHEMA_VERSION = 1
_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS pull_request (
    repo TEXT NOT NULL,
    number INTEGER NOT NULL,
    passes INTEGER,
    verdict TEXT,
    saved_at TEXT NOT NULL,
    PRIMARY KEY (repo, number)
);
CREATE TABLE IF NOT EXISTS finding (
    repo TEXT NOT NULL,
    pull_request INTEGER NOT NULL,
    number INTEGER NOT NULL,
    tier TEXT NOT NULL,
    outcome TEXT NOT NULL,
    up INTEGER NOT NULL DEFAULT 0,
    down INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (repo, pull_request, number)
);
CREATE TABLE IF NOT EXISTS finding_lens (
    repo TEXT NOT NULL,
    pull_request INTEGER NOT NULL,
    number INTEGER NOT NULL,
    lens TEXT NOT NULL,
    PRIMARY KEY (repo, pull_request, number, lens)
);
"""


@dataclass(frozen=True)
class SavedPullRequest:
    repo: str
    number: int
    passes: int | None
    verdict: str | None
    findings: int
    saved_at: str


class ScoreStore:
    """Scored pull requests in a SQLite file; ``with ScoreStore(path) as store:`` opens it and closes it."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.executescript(_SCHEMA)
        row = self._conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            with self._conn:
                self._conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        elif row[0] != SCHEMA_VERSION:
            self._conn.close()
            raise ValueError(f"{path} has schema version {row[0]}; this tool writes version {SCHEMA_VERSION}")

    def __enter__(self) -> "ScoreStore":
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._conn.close()

    def save(self, repo: str, number: int, score: PullRequestScore, saved_at: datetime | None = None) -> None:
        """Store one pull request, replacing whatever was saved for it before, in one transaction."""
        stamp = (saved_at or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._conn:
            for table in ("finding_lens", "finding"):
                self._conn.execute(f"DELETE FROM {table} WHERE repo = ? AND pull_request = ?", (repo, number))
            self._conn.execute(
                "INSERT OR REPLACE INTO pull_request (repo, number, passes, verdict, saved_at) VALUES (?, ?, ?, ?, ?)",
                (repo, number, score.passes, score.verdict, stamp),
            )
            for finding in score.findings:
                self._conn.execute(
                    "INSERT INTO finding (repo, pull_request, number, tier, outcome, up, down) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (repo, number, finding.number, finding.tier, finding.outcome, finding.up, finding.down),
                )
                self._conn.executemany(
                    "INSERT INTO finding_lens (repo, pull_request, number, lens) VALUES (?, ?, ?, ?)",
                    [(repo, number, finding.number, lens) for lens in finding.lenses],
                )

    def lens_totals(self, repos: Collection[str] | None = None) -> dict[str, Counter[str]]:
        """Per lens, the same counts as ``scorecard.tally``: findings, each outcome, thumbs up and down."""
        where, params = self._repo_filter("f.repo", repos)
        rows = self._conn.execute(
            "SELECT l.lens, f.outcome, COUNT(*), SUM(f.up), SUM(f.down) FROM finding f "
            "JOIN finding_lens l ON l.repo = f.repo AND l.pull_request = f.pull_request AND l.number = f.number "
            f"{where} GROUP BY l.lens, f.outcome",
            params,
        ).fetchall()
        totals: dict[str, Counter[str]] = {}
        for lens, outcome, count, up, down in rows:
            row = totals.setdefault(lens, Counter())
            row["findings"] += count
            row[outcome] += count
            row["up"] += up
            row["down"] += down
        return totals

    def pull_requests(self, repos: Collection[str] | None = None) -> list[SavedPullRequest]:
        """The saved pull requests, oldest number first within each repo, with their finding counts."""
        where, params = self._repo_filter("p.repo", repos)
        rows = self._conn.execute(
            "SELECT p.repo, p.number, p.passes, p.verdict, COUNT(f.number), p.saved_at FROM pull_request p "
            "LEFT JOIN finding f ON f.repo = p.repo AND f.pull_request = p.number "
            f"{where} GROUP BY p.repo, p.number ORDER BY p.repo, p.number",
            params,
        ).fetchall()
        return [SavedPullRequest(*row) for row in rows]

    @staticmethod
    def _repo_filter(column: str, repos: Collection[str] | None) -> tuple[str, list[str]]:
        if not repos:
            return "", []
        return f"WHERE {column} IN ({', '.join('?' for _ in repos)})", list(repos)
