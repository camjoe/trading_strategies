from __future__ import annotations

import os

from common.files import latest_by_mtime, modified_at_iso, sorted_by_mtime_desc


def test_sorted_by_mtime_desc_orders_newest_first(tmp_path) -> None:
    older = tmp_path / "older.txt"
    newer = tmp_path / "newer.txt"
    older.write_text("older", encoding="utf-8")
    newer.write_text("newer", encoding="utf-8")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))

    assert sorted_by_mtime_desc([older, newer]) == [newer, older]
    assert latest_by_mtime([older, newer]) == newer


def test_sorted_by_mtime_desc_ties_by_name_descending(tmp_path) -> None:
    first = tmp_path / "data_1.json"
    last = tmp_path / "data_3.json"
    first.write_text("1", encoding="utf-8")
    last.write_text("3", encoding="utf-8")
    os.utime(first, (100, 100))
    os.utime(last, (100, 100))

    assert sorted_by_mtime_desc([first, last]) == [last, first]


def test_latest_by_mtime_returns_none_for_empty_iterable() -> None:
    assert latest_by_mtime([]) is None


def test_modified_at_iso_is_utc_iso_timestamp(tmp_path) -> None:
    path = tmp_path / "file.txt"
    path.write_text("content", encoding="utf-8")
    os.utime(path, (0, 0))

    assert modified_at_iso(path) == "1970-01-01T00:00:00+00:00"
