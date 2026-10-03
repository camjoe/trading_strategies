from trading.services.reporting._formatting import positions_summary_text


def test_positions_summary_text_sorts_and_truncates() -> None:
    count, text = positions_summary_text({"MSFT": 2.0, "AAPL": 5.0})
    assert count == 2
    assert text.startswith("AAPL")

    truncated_count, truncated_text = positions_summary_text({f"T{i}": float(i) for i in range(7)})
    assert truncated_count == 7
    assert truncated_text.endswith(", ...")
