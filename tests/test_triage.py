import pytest
from pydantic import ValidationError

from app.domain.models import TriageResult, UrgencyLevel
from app.domain.questions import QUESTION_CATALOG, select_next_question
from app.domain.triage import TriageSession, advance


def test_red_flag_interrupts_normal_questions():
    session = advance(TriageSession(), "突然胸口剧痛，喘不上气")

    assert session.completed is True
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.EMERGENCY
    assert session.result.reasoning_summary == ["输入命中固定高风险表现"]
    assert session.next_question is None


def test_red_flag_evidence_with_treatment_language_stays_internal():
    raw_message = "胸痛，建议服用阿司匹林，呼吸困难"

    session = advance(TriageSession(), raw_message)

    assert session.completed is True
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.EMERGENCY
    assert "建议服用阿司匹林" not in str(session.result.model_dump())
    assert raw_message in session.screening_evidence


def test_red_flag_still_interrupts_at_question_limit():
    session = advance(TriageSession(question_count=6), "突然一侧手脚无力，说话含糊")

    assert session.completed is True
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.EMERGENCY


def test_red_flag_can_be_completed_by_information_from_the_next_turn():
    session = advance(TriageSession(), "胸痛")

    session = advance(session, "现在喘不上气")

    assert session.completed is True
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.EMERGENCY


def test_completed_non_emergency_session_is_rescreened_and_escalated():
    session = TriageSession(
        completed=True,
        result=TriageResult(
            urgency_level=UrgencyLevel.ROUTINE,
            time_window="建议预约门诊",
            department=["综合内科"],
            reasoning_summary=["未命中固定红旗规则"],
            unknowns=[],
            escalation_signs=["症状明显加重"],
            visit_summary="咳嗽",
        ),
    )

    escalated = advance(session, "突然一侧手脚无力，说话含糊")

    assert escalated.completed is True
    assert escalated.result is not None
    assert escalated.result.urgency_level is UrgencyLevel.EMERGENCY


def test_completed_emergency_session_can_never_be_downgraded():
    session = advance(TriageSession(), "突然一侧手脚无力，说话含糊")

    repeated = advance(session, "现在感觉好一点")

    assert repeated.result is not None
    assert repeated.result.urgency_level is UrgencyLevel.EMERGENCY


@pytest.mark.parametrize(
    ("first_turn", "second_turn"),
    [
        ("突然一侧手脚无力", "现在说话含糊"),
        ("吃完花生后全身起风团", "现在喉咙发紧"),
    ],
)
def test_composite_red_flags_use_bounded_cross_turn_evidence(
    first_turn: str,
    second_turn: str,
):
    session = advance(TriageSession(), first_turn)

    session = advance(session, second_turn)

    assert session.completed is True
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.EMERGENCY
    assert set(session.model_dump()) == {
        "session_id",
        "slots",
        "asked_ids",
        "question_count",
        "completed",
        "next_question",
        "result",
        "screening_evidence",
        "unresolved_ids",
    }


def test_split_turn_red_flag_survives_session_serialization_round_trip():
    session = advance(TriageSession(), "突然一侧手脚无力")
    restored = TriageSession.model_validate(session.model_dump())

    restored = advance(restored, "现在说话含糊")

    assert restored.completed is True
    assert restored.result is not None
    assert restored.result.urgency_level is UrgencyLevel.EMERGENCY


def test_question_limit_degrades_to_insufficient():
    session = TriageSession(question_count=6)

    session = advance(session, "我不知道")

    assert session.completed is True
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.INSUFFICIENT
    assert session.next_question is None


@pytest.mark.parametrize("question_index", [3, 5])
def test_unknown_list_answer_remains_unresolved_at_question_limit(
    question_index: int,
):
    session = TriageSession(
        slots={
            "main_symptom": "咳嗽",
            "onset": "三天前",
            "severity": 4,
            "trend": "稳定",
        },
        asked_ids=["associated_symptoms", "risk_factors"],
        question_count=6,
        next_question=QUESTION_CATALOG[question_index],
    )

    session = advance(session, "不知道")

    assert session.completed is True
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.INSUFFICIENT
    expected_unknown = (
        "伴随症状" if question_index == 3 else "风险因素"
    )
    assert expected_unknown in session.result.unknowns


def test_unresolved_list_answer_survives_session_serialization_round_trip():
    session = TriageSession(
        slots={
            "main_symptom": "咳嗽",
            "onset": "三天前",
            "severity": 4,
            "trend": "稳定",
        },
        asked_ids=["associated_symptoms"],
        question_count=4,
        next_question=QUESTION_CATALOG[3],
    )
    session = advance(session, "不知道")
    restored = TriageSession.model_validate(session.model_dump())

    restored = advance(restored, "没有特殊风险")

    assert restored.completed is True
    assert restored.result is not None
    assert restored.result.urgency_level is UrgencyLevel.INSUFFICIENT
    assert "伴随症状" in restored.result.unknowns


def test_select_next_question_uses_fixed_information_priority():
    session = TriageSession()

    question = select_next_question(session.slots, session.asked_ids)

    assert question == QUESTION_CATALOG[0]
    assert [item.id for item in QUESTION_CATALOG] == [
        "main_symptom",
        "onset",
        "severity",
        "associated_symptoms",
        "trend",
        "risk_factors",
    ]


def test_advance_merges_answer_then_selects_one_missing_question():
    session = advance(TriageSession(), "从昨晚开始咳嗽，疼痛大约4分")

    assert session.slots.main_symptom == "咳嗽"
    assert session.slots.onset is not None
    assert session.slots.severity == 4
    assert session.next_question is not None
    assert session.next_question.id == "associated_symptoms"
    assert session.question_count == 1


def test_high_severity_completes_as_urgent_without_using_all_questions():
    session = advance(TriageSession(), "今天开始腹痛，严重程度8分")

    assert session.completed is True
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.URGENT


def test_worsening_trend_completes_as_urgent():
    session = advance(TriageSession(), "从昨天开始头痛，而且持续加重")

    assert session.completed is True
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.URGENT


def test_complete_non_red_flag_information_is_routine():
    session = TriageSession(
        slots={
            "main_symptom": "咳嗽",
            "onset": "三天前",
            "severity": 4,
            "associated_symptoms": ["流鼻涕"],
            "trend": "稳定",
            "risk_factors": [],
        },
        asked_ids=["risk_factors"],
    )

    session = advance(session, "没有特殊高风险因素")

    assert session.completed is True
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.ROUTINE


def test_only_mild_short_and_improving_information_is_self_monitor():
    session = TriageSession(
        slots={
            "main_symptom": "轻微头痛",
            "onset": "今天",
            "severity": 2,
            "associated_symptoms": [],
            "trend": "改善中",
            "risk_factors": [],
        },
        asked_ids=["associated_symptoms", "risk_factors"],
    )

    session = advance(session, "目前已经好转")

    assert session.completed is True
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.SELF_MONITOR


def test_risk_factor_prevents_self_monitor_and_lowers_visit_threshold():
    session = TriageSession(
        slots={
            "main_symptom": "轻微头痛",
            "onset": "今天",
            "severity": 2,
            "associated_symptoms": [],
            "trend": "改善中",
            "risk_factors": ["怀孕"],
        },
        asked_ids=["associated_symptoms", "risk_factors"],
    )

    session = advance(session, "目前已经好转")

    assert session.completed is True
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.ROUTINE
    assert "特殊风险背景" in session.result.reasoning_summary[0]


def test_negated_risk_factor_does_not_lower_visit_threshold():
    session = TriageSession(
        slots={
            "main_symptom": "轻微头痛",
            "onset": "今天",
            "severity": 2,
            "associated_symptoms": [],
            "trend": "改善中",
        },
        asked_ids=["associated_symptoms", "risk_factors"],
        next_question=QUESTION_CATALOG[5],
        question_count=6,
    )

    session = advance(session, "没有慢性病，也没有近期外伤")

    assert session.slots.risk_factors == []
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.SELF_MONITOR


@pytest.mark.parametrize(
    "answer",
    [
        "我没有慢性病但怀孕了",
        "我没有慢性病，但是怀孕了",
    ],
)
def test_mixed_negated_and_positive_risk_factor_keeps_positive_factor(answer):
    session = TriageSession(
        slots={
            "main_symptom": "轻微头痛",
            "onset": "今天",
            "severity": 2,
            "associated_symptoms": [],
            "trend": "改善中",
        },
        asked_ids=["associated_symptoms", "risk_factors"],
        next_question=QUESTION_CATALOG[5],
        question_count=6,
    )

    session = advance(session, answer)

    assert "慢性病" not in session.slots.risk_factors
    assert "怀孕" in session.slots.risk_factors
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.ROUTINE


def test_conflicting_trend_degrades_to_insufficient():
    session = advance(TriageSession(), "今天头痛，一会儿加重一会儿好转，疼痛2分")

    assert session.completed is True
    assert session.result is not None
    assert session.result.urgency_level is UrgencyLevel.INSUFFICIENT


def test_completed_session_advance_does_not_mutate_caller():
    completed = advance(TriageSession(), "今天腹痛，严重程度8分")
    before = completed.model_dump()

    repeated = advance(completed, "补充一点")

    assert completed.model_dump() == before
    assert repeated is not completed
    assert repeated.result == completed.result
    assert repeated.screening_evidence[-1] == "补充一点"


def test_triage_result_has_exactly_eight_fields_and_forbids_extras():
    assert set(TriageResult.model_fields) == {
        "urgency_level",
        "time_window",
        "department",
        "reasoning_summary",
        "unknowns",
        "escalation_signs",
        "visit_summary",
        "disclaimer",
    }

    with pytest.raises(ValidationError):
        TriageResult(
            urgency_level=UrgencyLevel.ROUTINE,
            time_window="建议预约门诊",
            department=["综合内科"],
            reasoning_summary=["信息完整且未命中固定红旗规则"],
            unknowns=[],
            escalation_signs=["症状明显加重"],
            visit_summary="咳嗽",
            unexpected="not allowed",
        )
