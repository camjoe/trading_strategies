from pathlib import Path

from scripts.documentation_ui.api import build_registry as api_build
from scripts.documentation_ui.api.registry import API_REGISTRY_REL, ROUTES_DIR
from scripts.documentation_ui.software import build_registry as software_build
from scripts.documentation_ui.software.registry import SOFTWARE_REGISTRY_REL


def test_the_software_registry_is_written_with_unix_line_endings(tmp_path: Path) -> None:
    (tmp_path / "requirements-base.txt").write_text("requests==2.0.0\n", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("pytest==8.0.0\n", encoding="utf-8")
    registry = tmp_path / SOFTWARE_REGISTRY_REL
    registry.parent.mkdir(parents=True)

    software_build.run_build(tmp_path)

    assert registry.read_bytes().endswith(b"}\n")
    assert b"\r\n" not in registry.read_bytes()


def test_the_api_registry_is_written_with_unix_line_endings(tmp_path: Path) -> None:
    (tmp_path / ROUTES_DIR).mkdir(parents=True)
    registry = tmp_path / API_REGISTRY_REL
    registry.parent.mkdir(parents=True)

    api_build.run_build(tmp_path)

    assert registry.read_bytes().endswith(b"}\n")
    assert b"\r\n" not in registry.read_bytes()
