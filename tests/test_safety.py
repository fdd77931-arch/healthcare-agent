import pytest

from app.domain.models import TriageResult, UrgencyLevel
from app.domain.safety import validate_result


def make_result(
    urgency_level: UrgencyLevel = UrgencyLevel.ROUTINE,
    time_window: str = "建议预约门诊",
    **overrides,
) -> TriageResult:
    values = {
        "urgency_level": urgency_level,
        "time_window": time_window,
        "department": ["综合内科"],
        "reasoning_summary": ["目前信息未显示固定红旗信号"],
        "unknowns": ["既往史"],
        "escalation_signs": ["症状明显加重"],
        "visit_summary": "胸部不适",
    }
    values.update(overrides)
    return TriageResult(**values)


def test_emergency_result_requires_immediate_time_window():
    result = make_result(
        urgency_level=UrgencyLevel.EMERGENCY,
        time_window="下周",
        department=["急诊"],
        reasoning_summary=["出现高风险表现"],
        unknowns=[],
        escalation_signs=[],
        visit_summary="胸痛",
    )

    with pytest.raises(ValueError, match="immediate"):
        validate_result(result)


@pytest.mark.parametrize(
    "time_window",
    [
        "下周立即去急诊",
        "以后立即拨打120",
        "先观察几天，再立即去急诊",
        "一周后立即去急诊",
        "两周后立即拨打120",
        "3天后立即去急诊",
        "4周后立即去急诊",
        "过几天立即去急诊",
        "稍后立即拨打120",
    ],
)
def test_emergency_result_rejects_delaying_language_even_with_immediate_marker(
    time_window: str,
):
    result = make_result(
        urgency_level=UrgencyLevel.EMERGENCY,
        time_window=time_window,
        department=["急诊"],
    )

    with pytest.raises(ValueError, match="time window"):
        validate_result(result)


def test_rejects_diagnostic_language():
    result = make_result(visit_summary="你得了心肌梗死")

    with pytest.raises(ValueError, match="diagnostic language"):
        validate_result(result)


@pytest.mark.parametrize(
    "diagnostic_text",
    [
        "诊断为心肌梗死",
        "这是心肌梗死",
        "这是冠心病",
        "你患有冠心病",
        "你患上了糖尿病",
    ],
)
def test_rejects_additional_obvious_diagnostic_language(
    diagnostic_text: str,
):
    result = make_result(visit_summary=diagnostic_text)

    with pytest.raises(ValueError, match="diagnostic language"):
        validate_result(result)


@pytest.mark.parametrize(
    "instruction",
    ["建议口服阿司匹林", "建议服用阿司匹林", "建议吃药"],
)
def test_rejects_treatment_instruction_language(instruction: str):
    result = make_result(reasoning_summary=[instruction])

    with pytest.raises(ValueError, match="treatment language"):
        validate_result(result)


@pytest.mark.parametrize(
    "instruction",
    [
        "每天服用一片",
        "每次服用两粒",
        "每天吃一片",
        "每日饭后吃两片",
    ],
)
def test_rejects_dosage_language_in_any_output_field(instruction: str):
    result = make_result(reasoning_summary=[instruction])

    with pytest.raises(ValueError, match="dosage language"):
        validate_result(result)


@pytest.mark.parametrize(
    ("urgency_level", "time_window"),
    [
        (UrgencyLevel.EMERGENCY, "请立即拨打120或前往急诊"),
        (UrgencyLevel.URGENT, "建议今天尽快就医"),
        (UrgencyLevel.ROUTINE, "建议预约门诊"),
        (UrgencyLevel.SELF_MONITOR, "可先观察24小时"),
        (UrgencyLevel.INSUFFICIENT, "信息不足，请咨询人工医疗渠道"),
    ],
)
def test_accepts_consistent_time_window(
    urgency_level: UrgencyLevel,
    time_window: str,
):
    result = make_result(urgency_level=urgency_level, time_window=time_window)

    assert validate_result(result) is result


@pytest.mark.parametrize(
    ("urgency_level", "time_window"),
    [
        (UrgencyLevel.URGENT, "下周预约"),
        (UrgencyLevel.ROUTINE, "立即拨打120"),
        (UrgencyLevel.SELF_MONITOR, "建议今天急诊就医"),
        (UrgencyLevel.INSUFFICIENT, "可以在家观察"),
    ],
)
def test_rejects_time_windows_that_conflict_with_urgency(
    urgency_level: UrgencyLevel,
    time_window: str,
):
    result = make_result(urgency_level=urgency_level, time_window=time_window)

    with pytest.raises(ValueError, match="time window"):
        validate_result(result)
