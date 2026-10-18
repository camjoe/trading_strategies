"""Shared helpers for the repository-check script tests."""

from __future__ import annotations

from pathlib import Path


def write_file(path: Path, content: str) -> Path:
    """Write *content* to *path*, creating parent directories, and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# A readiness comment in the layout that carries kind, prediction, passes, and who closed each finding.
NEW_BODY = (
    "<!-- pr-readiness -->\n## PR readiness: READY\n\nReviewed `a` · 2026-10-18 · pass 3 · current\n\n"
    "#### 🟠 Concerns\n"
    "- [ ] **4. Still open.** `src/a.py:7`: text. → decision: keep or drop X? [Break it, Operator · design · pass 2]\n\n"
    "<details>\n<summary>🟡 Notes (1 open)</summary>\n\n#### 🟡 Notes (1)\n"
    "- [ ] **5. A note.** `src/a.py:9`: text. → info: what does the host run? "
    "[Break it, rated CONCERN; lowered to NOTE because unconfirmed · bug · pass 3]\n\n</details>\n\n"
    "<details>\n<summary>✓ Closed (3)</summary>\n\n#### Closed (3)\n"
    "- [x] **1. Fixed by the fixer.** `src/a.py:1`: Fixed in `abc1234` (pass 2, by fixer): ok. [Operator · bug · pass 1]\n"
    "- [x] **2. Fixed by the author.** `docs/a.md:2`: Fixed in `def5678` (pass 3, by author): ok. "
    "[Test skeptic · test · pass 1]\n"
    "- [x] **3. Decided.** `src/b.py:3`: Decided (pass 3, by owner): keep it. [Simplifier · wording · pass 2]\n"
    "  *Decision: Approved by the owner on 2026-10-18: keep it.*\n"
    "</details>\n"
)
