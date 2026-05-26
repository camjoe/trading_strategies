from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def job_root(tmp_path: Path) -> Path:
    """A tmp_path with the ``local/logs`` directory pre-created.

    Runtime job tests that write or read log files can use this fixture
    instead of creating the directory manually in each test.
    """
    (tmp_path / "local" / "logs").mkdir(parents=True)
    return tmp_path
