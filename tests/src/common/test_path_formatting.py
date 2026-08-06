from __future__ import annotations

from common.paths.formatting import relative_posix


def test_relative_posix_uses_forward_slashes(tmp_path) -> None:
    path = tmp_path / "a" / "b" / "file.txt"
    path.parent.mkdir(parents=True)
    path.write_text("x", encoding="utf-8")

    assert relative_posix(path, tmp_path) == "a/b/file.txt"
