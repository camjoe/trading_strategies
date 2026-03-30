import sqlite3
from trading.profile_source import AccountProfileSource, JsonAccountProfileSource
from trading.services.profiles_service import apply_account_profiles as apply_account_profiles_impl
from trading.services.profiles_service import load_account_profiles_from_source as load_account_profiles_from_source_impl

def load_account_profiles_from_source(source: AccountProfileSource) -> list[dict[str, object]]:
    return load_account_profiles_from_source_impl(source)


def load_account_profiles(file_path: str) -> list[dict[str, object]]:
    return load_account_profiles_from_source(JsonAccountProfileSource(file_path))


def apply_account_profiles(
    conn: sqlite3.Connection,
    profiles: list[dict[str, object]],
    create_missing: bool,
) -> tuple[int, int, int]:
    return apply_account_profiles_impl(conn, profiles, create_missing)
