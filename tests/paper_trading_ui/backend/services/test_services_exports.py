from __future__ import annotations

import pytest
from fastapi import HTTPException

from paper_trading_ui.backend.services import exports as services_exports


def test_resolve_csv_export_file_guards_path_and_suffix(monkeypatch, tmp_path) -> None:
    base = tmp_path / "exports"
    base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(services_exports, "EXPORTS_DIR", base)

    with pytest.raises(HTTPException) as bad_suffix:
        services_exports.resolve_csv_export_file("db_csv_20260101", "accounts.txt")
    assert bad_suffix.value.status_code == 400

    with pytest.raises(HTTPException) as bad_path:
        services_exports.resolve_csv_export_file("..", "escape.csv")
    assert bad_path.value.status_code == 400


def test_list_and_preview_csv_exports(monkeypatch, tmp_path) -> None:
    base = tmp_path / "exports"
    older = base / "db_csv_20260101"
    newer = base / "db_csv_20260102"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)

    (newer / "accounts.csv").write_text("name,equity\nacct_a,100\nacct_b,200\n", encoding="utf-8")
    (older / "trades.csv").write_text("ticker,qty\nAAPL,1\n", encoding="utf-8")

    monkeypatch.setattr(services_exports, "EXPORTS_DIR", base)

    listing = services_exports.list_csv_exports()
    assert [item["name"] for item in listing["exports"]] == ["db_csv_20260102", "db_csv_20260101"]
    assert listing["exports"][0]["files"][0]["name"] == "accounts.csv"

    preview = services_exports.preview_csv_export("db_csv_20260102", "accounts.csv", limit=1)
    assert preview["header"] == ["name", "equity"]
    assert preview["rows"] == [["acct_a", "100"]]
    assert preview["returned"] == 1
    assert preview["truncated"] is True


def test_preview_csv_export_404_for_missing_file(monkeypatch, tmp_path) -> None:
    base = tmp_path / "exports"
    (base / "db_csv_20260102").mkdir(parents=True)
    monkeypatch.setattr(services_exports, "EXPORTS_DIR", base)

    with pytest.raises(HTTPException) as exc_info:
        services_exports.preview_csv_export("db_csv_20260102", "missing.csv", limit=10)
    assert exc_info.value.status_code == 404
