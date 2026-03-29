import sqlite3

import pytest

from trading.database import db_coercion


@pytest.fixture
def sample_row() -> sqlite3.Row:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT ? AS txt, ? AS num_txt, ? AS int_txt, ? AS missing",
            ("abc", "1.25", "7", None),
        ).fetchone()
        assert row is not None
        return row
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("x", "x"),
        (123, "123"),
        (12.5, "12.5"),
        (True, "True"),
    ],
)
def test_coerce_str_converts_supported_values(raw: object, expected: str) -> None:
    assert db_coercion.coerce_str(raw) == expected


def test_expect_str_rejects_none_with_field_name() -> None:
    with pytest.raises(ValueError, match="ticker cannot be null"):
        db_coercion.expect_str(None, "ticker")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1, 1.0),
        ("1.5", 1.5),
        (2.25, 2.25),
    ],
)
def test_coerce_float_accepts_numeric_like_values(raw: object, expected: float) -> None:
    assert db_coercion.coerce_float(raw) == expected


def test_coerce_float_rejects_non_convertible_type() -> None:
    with pytest.raises(ValueError, match="Expected float-convertible value, got list"):
        db_coercion.coerce_float([1, 2])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, False),
        (1, True),
        ("true", True),
        (" YES ", True),
        ("off", False),
    ],
)
def test_coerce_bool_accepts_common_representations(raw: object, expected: bool) -> None:
    assert db_coercion.coerce_bool(raw) is expected


def test_coerce_bool_rejects_unrecognized_string() -> None:
    with pytest.raises(ValueError, match="Invalid boolean value"):
        db_coercion.coerce_bool("maybe")


def test_expect_int_rejects_none_with_field_name() -> None:
    with pytest.raises(ValueError, match="count cannot be null"):
        db_coercion.expect_int(None, "count")


def test_row_helpers_coerce_and_expect(sample_row: sqlite3.Row) -> None:
    assert db_coercion.row_str(sample_row, "txt") == "abc"
    assert db_coercion.row_expect_str(sample_row, "txt") == "abc"
    assert db_coercion.row_float(sample_row, "num_txt") == 1.25
    assert db_coercion.row_expect_float(sample_row, "num_txt") == 1.25
    assert db_coercion.row_int(sample_row, "int_txt") == 7
    assert db_coercion.row_expect_int(sample_row, "int_txt") == 7


def test_row_expect_helpers_reject_null_values(sample_row: sqlite3.Row) -> None:
    with pytest.raises(ValueError, match="missing cannot be null"):
        db_coercion.row_expect_str(sample_row, "missing")


def test_to_float_obj_delegates_to_expect_float() -> None:
    assert db_coercion.to_float_obj("2.5") == 2.5


def test_to_int_obj_delegates_to_expect_int() -> None:
    assert db_coercion.to_int_obj("3") == 3
