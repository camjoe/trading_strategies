from trading.models.settings import GlobalSettingsChangeEvent
from trading.services.change_history_presentation import render_settings_change_lines


def _event(changed_fields: dict[str, dict[str, object]]) -> GlobalSettingsChangeEvent:
    return GlobalSettingsChangeEvent(
        id=1,
        settings_group="promotion",
        changed_fields=changed_fields,
        created_at="2026-08-13T00:00:00Z",
    )


def test_empty_events_returns_empty_list() -> None:
    assert render_settings_change_lines([]) == []


def test_renders_one_line_per_event_with_old_new() -> None:
    event = _event({"min_confidence": {"old": 0.5, "new": 0.7}})
    lines = render_settings_change_lines([event])
    assert lines == ["- 2026-08-13T00:00:00Z | promotion | min_confidence: 0.5 -> 0.7"]


def test_renders_multiple_changed_fields_comma_separated_in_order() -> None:
    event = _event({"a": {"old": 1, "new": 2}, "b": {"old": "x", "new": "y"}})
    lines = render_settings_change_lines([event])
    assert lines[0] == "- 2026-08-13T00:00:00Z | promotion | a: 1 -> 2, b: 'x' -> 'y'"
