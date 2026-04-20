from trading.domain.evaluation_models import StrategyEvaluationArtifact


def test_strategy_evaluation_artifact_payload_defaults() -> None:
    artifact = StrategyEvaluationArtifact()

    payload = artifact.to_payload()

    assert payload["meta"]["artifact_version"] == "phase2.v1"
    assert payload["basic"]["requested_strategy"] is None
    assert payload["backtest"]["available"] is False
    assert payload["walk_forward"]["run_ids"] == []
    assert payload["paper_live"]["strategy_isolated"] is False
    assert payload["confidence"]["overall_confidence"] == 0.0
    assert payload["diagnostics"]["data_gaps"] == []
