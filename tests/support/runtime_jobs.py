from __future__ import annotations

import importlib
import sys
from pathlib import Path


def load_runtime_job(module_name: str):
    return importlib.import_module(module_name)


def run_runtime_job_main(monkeypatch, tmp_path: Path, module_name: str, argv: list[str]) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        [module_name.rsplit(".", 1)[-1]] + argv + ["--repo-root", str(tmp_path)],
    )
    (tmp_path / "local" / "logs").mkdir(parents=True, exist_ok=True)
    return load_runtime_job(module_name).main()


__all__ = [
    "load_runtime_job",
    "run_runtime_job_main",
]
