"""Fixed, safety-reviewed question catalog for the bounded demo flow."""

from app.domain.models import TriageQuestion, TriageSlots


QUESTION_CATALOG: tuple[TriageQuestion, ...] = (
    TriageQuestion(
        id="main_symptom",
        prompt="目前最困扰你的症状是什么？主要在身体哪个部位？",
        rationale="明确主要症状和部位有助于判断下一步需要了解什么。",
        answer_type="free_text",
    ),
    TriageQuestion(
        id="onset",
        prompt="症状从什么时候开始，持续多久了？",
        rationale="起始时间和持续时长会影响就医时间建议。",
        answer_type="time_description",
    ),
    TriageQuestion(
        id="severity",
        prompt="如果用 0–10 分表示不适程度，目前大约是几分？",
        rationale="严重程度及其对活动的影响可能改变行动等级。",
        answer_type="zero_to_ten",
    ),
    TriageQuestion(
        id="associated_symptoms",
        prompt="还有哪些同时出现的症状？如果没有，也请说明。",
        rationale="关键伴随表现可提示是否需要更快就医。",
        answer_type="free_text_list",
    ),
    TriageQuestion(
        id="trend",
        prompt="症状是在加重、保持不变，还是逐渐好转？",
        rationale="变化趋势是判断能否继续观察的重要依据。",
        answer_type="trend_choice",
    ),
    TriageQuestion(
        id="risk_factors",
        prompt="是否有孕产、慢性病、近期外伤或其他特殊风险情况？",
        rationale="高风险背景可能降低就医门槛。",
        answer_type="free_text_list",
    ),
)


def _is_missing(slots: TriageSlots, question_id: str) -> bool:
    value = getattr(slots, question_id)
    if isinstance(value, list):
        return not value
    return value is None


def select_next_question(
    slots: TriageSlots,
    asked_ids: list[str],
) -> TriageQuestion | None:
    """Return the first missing, not-yet-asked question in fixed priority order."""
    asked = set(asked_ids)
    return next(
        (
            question
            for question in QUESTION_CATALOG
            if question.id not in asked and _is_missing(slots, question.id)
        ),
        None,
    )
