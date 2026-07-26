import pytest

from tests.support.promotion import make_ready_evaluation
from trading.models.promotion import PromotionAssessment
from trading.services.promotion import (
    assessment as promotion_assessment,
    fetch_promotion_assessment,
)


def test_fetch_promotion_assessment_uses_evaluation_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str | None]] = []

    def fake_fetch_strategy_evaluation(conn, *, account_name: str, strategy_name: str | None):
        calls.append((account_name, strategy_name))
        return make_ready_evaluation(account_name=account_name, strategy_name=strategy_name or "trend_v1")

    monkeypatch.setattr(promotion_assessment, "fetch_strategy_evaluation", fake_fetch_strategy_evaluation)

    assessment = fetch_promotion_assessment(
        object(),  # type: ignore[arg-type]
        account_name="acct_service",
        strategy_name="trend_v1",
    )

    assert calls == [("acct_service", "trend_v1")]
    assert assessment.stage == "promotion_review"
    assert assessment.ready_for_live is True
