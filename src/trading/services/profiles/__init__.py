"""Profiles service package.

This package is the stable public profile-application surface.
"""

from __future__ import annotations

from trading.services.books.rotation.config_parser import parse_book_rotation_config_from_profile
from trading.services.profiles.application import (
    apply_account_profiles,
    apply_book_rotation_settings,
    load_account_profiles,
    load_account_profiles_from_source,
)

__all__ = [
    "apply_account_profiles",
    "apply_book_rotation_settings",
    "load_account_profiles",
    "load_account_profiles_from_source",
    "parse_book_rotation_config_from_profile",
]
