"""Paths an unattended fixer must never change.

Broker, database, execution, and risk code comes from the review-scope rules that already mark them
high risk, so the two lists cannot drift apart. The rest are the pipeline's own controls and the places
that hold decisions or secrets.
"""

from collections.abc import Iterable

from scripts.checks.repo.review_scope_check import SCOPE_RULES

_EXTRA_GUARDS = (
    ("scripts/forge/", "the forge tool and its checks"),
    (".github/workflows/", "the pipeline's workflows"),
    (".ai/skills/", "the skills"),
    ("AGENTS.md", "the standing authorizations"),
    ("CLAUDE.md", "the standing authorizations"),
    ("docs/adr/", "accepted decisions"),
    (".env", "credentials and environment"),
    ("local/", "private research and parameters"),
)


def guarded_paths_touched(paths: Iterable[str]) -> list[str]:
    """One ``path: reason`` entry for each path in *paths* that falls under a guarded prefix."""
    guards = tuple((rule.prefix, rule.reason) for rule in SCOPE_RULES if rule.high_risk) + _EXTRA_GUARDS
    found: list[str] = []
    for path in paths:
        normalized = path.replace("\\", "/")
        for prefix, reason in guards:
            if normalized.startswith(prefix):
                found.append(f"{path}: {reason}")
                break
    return found
