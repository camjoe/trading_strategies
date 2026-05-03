def in_placeholders(values: tuple[object, ...] | list[object]) -> str:
    """Return comma-separated ``?`` placeholders for a SQL IN clause."""
    return ",".join(["?"] * len(values))
