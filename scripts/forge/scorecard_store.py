"""A small SQLite store for scored review findings.

Standard library only, and it knows nothing about a forge or a project: rows are keyed by a ``repo`` label, so
one file can hold the reviews of several projects.
"""

import sqlite3
from collections import Counter
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType

from scripts.forge.base import ForgeError
from scripts.forge.scorecard import PullRequestScore

SCHEMA_VERSION = 3
_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS pull_request (
    repo TEXT NOT NULL,
    number INTEGER NOT NULL,
    passes INTEGER,
    verdict TEXT,
    saved_at TEXT NOT NULL,
    title TEXT,
    author TEXT,
    base_ref TEXT,
    head_ref TEXT,
    created_at TEXT,
    merged_at TEXT,
    additions INTEGER,
    deletions INTEGER,
    commit_count INTEGER,
    PRIMARY KEY (repo, number)
);
CREATE TABLE IF NOT EXISTS pull_request_file (
    repo TEXT NOT NULL,
    pull_request INTEGER NOT NULL,
    path TEXT NOT NULL,
    area TEXT NOT NULL,
    PRIMARY KEY (repo, pull_request, path)
);
CREATE TABLE IF NOT EXISTS finding (
    repo TEXT NOT NULL,
    pull_request INTEGER NOT NULL,
    number INTEGER NOT NULL,
    tier TEXT NOT NULL,
    outcome TEXT NOT NULL,
    up INTEGER NOT NULL DEFAULT 0,
    down INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    path TEXT,
    line INTEGER,
    area TEXT,
    fixed_in TEXT,
    lowered TEXT,
    text TEXT NOT NULL DEFAULT '',
    kind TEXT,
    needs TEXT,
    opened_pass INTEGER,
    closed_pass INTEGER,
    closed_by TEXT,
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
_V2_TO_V3 = (
    "ALTER TABLE finding ADD COLUMN kind TEXT",
    "ALTER TABLE finding ADD COLUMN needs TEXT",
    "ALTER TABLE finding ADD COLUMN opened_pass INTEGER",
    "ALTER TABLE finding ADD COLUMN closed_pass INTEGER",
    "ALTER TABLE finding ADD COLUMN closed_by TEXT",
)
NOT_RECORDED = "(not recorded)"


class ScoreStoreError(ForgeError):
    """The database file cannot be opened, read, or written."""


@dataclass(frozen=True)
class SavedPullRequest:
    repo: str
    number: int
    passes: int | None
    verdict: str | None
    findings: int
    saved_at: str


@contextmanager
def _failures(path: Path) -> Iterator[None]:
    """Turn a database or file-system error into a :class:`ScoreStoreError` that names the file."""
    try:
        yield
    except (sqlite3.Error, OSError) as exc:
        raise ScoreStoreError(f"{path}: {exc}. Move or delete the file to start a new one.") from exc


class ScoreStore:
    """Scored pull requests in a SQLite file; ``with ScoreStore(path) as store:`` opens it and closes it."""

    def __init__(self, path: Path) -> None:
        self._path = path
        with _failures(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(path)
            try:
                self._prepare(path)
            except sqlite3.Error, ScoreStoreError:
                self._conn.close()
                raise

    def _prepare(self, path: Path) -> None:
        """Create the schema in a new file, migrate version 2, and refuse any other file without changing it."""
        tables = {row[0] for row in self._conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "schema_version" not in tables:
            if tables:
                raise ScoreStoreError(
                    f"{path} is not a scorecard database. Move or delete the file to start a new one."
                )
            with self._conn:
                self._conn.executescript(_SCHEMA)
                self._conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            return
        row = self._conn.execute("SELECT version FROM schema_version").fetchone()
        version = row[0] if row else None
        if version == 2:
            with self._conn:
                for statement in _V2_TO_V3:
                    self._conn.execute(statement)
                self._conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
        elif version != SCHEMA_VERSION:
            raise ScoreStoreError(
                f"{path} has schema version {version}; this tool writes version {SCHEMA_VERSION}. "
                "Move or delete the file to start a new one."
            )

    def __enter__(self) -> "ScoreStore":
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._conn.close()

    def save(self, repo: str, number: int, score: PullRequestScore, saved_at: str | None = None) -> None:
        """Store one pull request, replacing whatever was saved for it before, in one transaction.

        *saved_at* is an ISO UTC timestamp (default: now, written with the standard library). A finding number
        that repeats keeps its last occurrence.
        """
        stamp = saved_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        findings = {finding.number: finding for finding in score.findings}
        with _failures(self._path), self._conn:
            for table in ("finding_lens", "finding", "pull_request_file"):
                self._conn.execute(f"DELETE FROM {table} WHERE repo = ? AND pull_request = ?", (repo, number))
            info = score.details
            self._conn.execute(
                "INSERT OR REPLACE INTO pull_request (repo, number, passes, verdict, saved_at, title, author, base_ref, "
                "head_ref, created_at, merged_at, additions, deletions, commit_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    repo,
                    number,
                    score.passes,
                    score.verdict,
                    stamp,
                    info and info.title,
                    info and info.author,
                    info and info.base_ref,
                    info and info.head_ref,
                    info and info.created_at,
                    info and info.merged_at,
                    info and info.additions,
                    info and info.deletions,
                    info and info.commit_count,
                ),
            )
            self._conn.executemany(
                "INSERT INTO pull_request_file (repo, pull_request, path, area) VALUES (?, ?, ?, ?)",
                [(repo, number, path, area) for path, area in score.file_areas.items()],
            )
            for finding in findings.values():
                self._conn.execute(
                    "INSERT INTO finding (repo, pull_request, number, tier, outcome, up, down, title, path, line, area, "
                    "fixed_in, lowered, text, kind, needs, opened_pass, closed_pass, closed_by) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        repo,
                        number,
                        finding.number,
                        finding.tier,
                        finding.outcome,
                        finding.up,
                        finding.down,
                        finding.title,
                        finding.path,
                        finding.line,
                        finding.area,
                        finding.fixed_in,
                        finding.lowered,
                        finding.text,
                        finding.kind,
                        finding.needs,
                        finding.opened_pass,
                        finding.closed_pass,
                        finding.closed_by,
                    ),
                )
                self._conn.executemany(
                    "INSERT INTO finding_lens (repo, pull_request, number, lens) VALUES (?, ?, ?, ?)",
                    [(repo, number, finding.number, lens) for lens in finding.lenses],
                )

    def lens_totals(self, repos: Collection[str] | None = None) -> dict[str, Counter[str]]:
        """Per lens, the same counts as ``scorecard.tally``: findings, each outcome, thumbs up and down."""
        where, params = self._repo_filter("f.repo", repos)
        with _failures(self._path):
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

    def human_input(self, repos: Collection[str] | None = None) -> Counter[tuple[str, str]]:
        """Findings counted by what the reviewer predicted (``fix``, ``decision``, ``info``) and how each ended.

        How it ended is ``fixer``, ``author``, ``owner``, ``left open``, or ``(not recorded)`` for a finding from
        before the closing line said who closed it. A finding with no prediction counts under ``(not recorded)``.
        """
        where, params = self._repo_filter("repo", repos)
        with _failures(self._path):
            rows = self._conn.execute(
                f"SELECT needs, closed_by, outcome, COUNT(*) FROM finding {where} GROUP BY needs, closed_by, outcome",
                params,
            ).fetchall()
        counts: Counter[tuple[str, str]] = Counter()
        for needs, closed_by, outcome, count in rows:
            ended = closed_by or ("left open" if outcome == "left open" else NOT_RECORDED)
            counts[(needs or NOT_RECORDED, ended)] += count
        return counts

    def pull_requests(self, repos: Collection[str] | None = None) -> list[SavedPullRequest]:
        """The saved pull requests, oldest number first within each repo, with their finding counts."""
        where, params = self._repo_filter("p.repo", repos)
        with _failures(self._path):
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
