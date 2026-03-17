import sqlite3


def coerce_str(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def expect_str(value: object | None, field_name: str = "value") -> str:
    converted = coerce_str(value)
    if converted is None:
        raise ValueError(f"{field_name} cannot be null")
    return converted


def coerce_float(value: object | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        return float(value)
    raise ValueError(f"Expected float-convertible value, got {type(value).__name__}")


def expect_float(value: object | None, field_name: str = "value") -> float:
    converted = coerce_float(value)
    if converted is None:
        raise ValueError(f"{field_name} cannot be null")
    return converted


def coerce_int(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        return int(value)
    raise ValueError(f"Expected int-convertible value, got {type(value).__name__}")


def expect_int(value: object | None, field_name: str = "value") -> int:
    converted = coerce_int(value)
    if converted is None:
        raise ValueError(f"{field_name} cannot be null")
    return converted


def coerce_bool(value: object | None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"Invalid boolean value: {value}")


def row_str(row: sqlite3.Row, key: str) -> str | None:
    return coerce_str(row[key])


def row_expect_str(row: sqlite3.Row, key: str) -> str:
    return expect_str(row[key], key)


def row_float(row: sqlite3.Row, key: str) -> float | None:
    return coerce_float(row[key])


def row_expect_float(row: sqlite3.Row, key: str) -> float:
    return expect_float(row[key], key)


def row_int(row: sqlite3.Row, key: str) -> int | None:
    return coerce_int(row[key])


def row_expect_int(row: sqlite3.Row, key: str) -> int:
    return expect_int(row[key], key)


def to_float_obj(value: object) -> object:
    return expect_float(value)


def to_int_obj(value: object) -> object:
    return expect_int(value)
