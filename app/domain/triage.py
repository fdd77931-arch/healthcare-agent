"""Bounded deterministic triage state machine for demonstration use."""

import re
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain.models import (
    TriageQuestion,
    TriageResult,
    TriageSlots,
    UrgencyLevel,
)
from app.domain.questions import QUESTION_CATALOG, select_next_question
from app.domain.red_flags import detect_red_flags
from app.domain.safety import validate_result


MAX_QUESTIONS = 6
MAX_EVIDENCE_TURNS = 8
MAX_EVIDENCE_CHARS_PER_TURN = 240
EvidenceText = Annotated[
    str,
    StringConstraints(max_length=MAX_EVIDENCE_CHARS_PER_TURN),
]
UNKNOWN_MARKERS = ("不知道", "不清楚", "不确定", "说不清")
WORSENING_MARKERS = ("持续加重", "越来越重", "恶化", "加重")
IMPROVING_MARKERS = ("逐渐好转", "改善", "减轻", "缓解", "好转")
STABLE_MARKERS = ("保持不变", "没有变化", "差不多", "稳定", "不变")
SAFE_TREND_VALUES = ("持续加重", "改善中", "稳定", "冲突：同时描述加重和改善")
SHORT_ONSET_MARKERS = ("刚才", "刚刚", "今天", "数小时", "几小时", "一小时", "1小时")

SYMPTOM_MARKERS = (
    "胸痛",
    "胸口疼",
    "胸闷",
    "腹痛",
    "肚子疼",
    "头痛",
    "咳嗽",
    "发热",
    "发烧",
    "头晕",
    "恶心",
    "呕吐",
    "皮疹",
    "疼痛",
)
ASSOCIATED_SYMPTOM_MARKERS = (
    "发热",
    "发烧",
    "咳嗽",
    "流鼻涕",
    "恶心",
    "呕吐",
    "头晕",
    "乏力",
    "腹泻",
)
RISK_FACTOR_MARKERS = (
    "怀孕",
    "孕期",
    "产后",
    "慢性病",
    "高血压",
    "糖尿病",
    "心脏病",
    "近期外伤",
    "外伤",
)
SLOT_LABELS = {
    "main_symptom": "主要症状",
    "onset": "起始时间",
    "severity": "严重程度",
    "associated_symptoms": "伴随症状",
    "trend": "变化趋势",
    "risk_factors": "风险因素",
}


class TriageSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(default_factory=lambda: uuid4().hex)
    slots: TriageSlots = Field(default_factory=TriageSlots)
    asked_ids: list[str] = Field(default_factory=list)
    question_count: int = Field(default=0, ge=0)
    completed: bool = False
    next_question: TriageQuestion | None = None
    result: TriageResult | None = None
    screening_evidence: list[EvidenceText] = Field(
        default_factory=list,
        max_length=MAX_EVIDENCE_TURNS,
    )
    unresolved_ids: list[str] = Field(default_factory=list)


def _contains_unknown(text: str) -> bool:
    return any(marker in text for marker in UNKNOWN_MARKERS)


def _extract_main_symptom(text: str) -> str | None:
    return next((marker for marker in SYMPTOM_MARKERS if marker in text), None)


def _extract_onset(text: str) -> str | None:
    patterns = (
        r"(?:从)?(?:今天|昨天|昨晚|前天|刚才|刚刚)(?:开始)?",
        r"(?:从)?[一二两三四五六七八九十\d]+(?:分钟|小时|天|周|个月|月)前(?:开始)?",
        r"(?:持续|已经)[一二两三四五六七八九十\d]+(?:分钟|小时|天|周|个月|月)",
    )
    return next(
        (match.group(0) for pattern in patterns if (match := re.search(pattern, text))),
        None,
    )


def _extract_severity(text: str) -> int | None:
    score_match = re.search(r"(?<!\d)(10|[0-9])\s*(?:分|/10)", text)
    if score_match:
        return int(score_match.group(1))
    if any(marker in text for marker in ("剧烈", "非常严重", "很严重")):
        return 8
    if any(marker in text for marker in ("轻微", "有一点", "一点")):
        return 2
    return None


def _extract_trend(text: str) -> str | None:
    worsening = any(marker in text for marker in WORSENING_MARKERS)
    improving = any(marker in text for marker in IMPROVING_MARKERS)
    if worsening and improving:
        return "冲突：同时描述加重和改善"
    if worsening:
        return "持续加重"
    if improving:
        return "改善中"
    if any(marker in text for marker in STABLE_MARKERS):
        return "稳定"
    return None


def _extract_terms(text: str, markers: tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(marker for marker in markers if marker in text))


def _extract_positive_terms(text: str, markers: tuple[str, ...]) -> list[str]:
    negators = ("没有", "并无", "否认", "无", "未")
    positive: list[str] = []
    for marker in markers:
        position = text.find(marker)
        while position >= 0:
            prefix = text[max(0, position - 8) : position]
            local_clause = re.split(
                r"[，。；,;]|但是|不过|然而|但|而",
                prefix,
            )[-1]
            if not any(negator in local_clause for negator in negators):
                positive.append(marker)
                break
            position = text.find(marker, position + len(marker))
    return list(dict.fromkeys(positive))


def _remember_evidence(session: TriageSession, user_text: str) -> None:
    text = user_text.strip()
    if not text:
        return
    session.screening_evidence.append(text[:MAX_EVIDENCE_CHARS_PER_TURN])
    session.screening_evidence[:] = session.screening_evidence[
        -MAX_EVIDENCE_TURNS:
    ]


def _screen_for_red_flags(session: TriageSession):
    screening_text = " ".join(session.screening_evidence)
    normalized_text = screening_text.replace("胸口剧痛", "胸痛")
    return detect_red_flags(normalized_text, session.slots)


def _mark_resolved(session: TriageSession, question_id: str) -> None:
    session.unresolved_ids = [
        unresolved_id
        for unresolved_id in session.unresolved_ids
        if unresolved_id != question_id
    ]


def _mark_unresolved(session: TriageSession, question_id: str) -> None:
    if question_id not in session.unresolved_ids:
        session.unresolved_ids.append(question_id)


def _merge_answer(session: TriageSession, user_text: str) -> None:
    text = user_text.strip()
    answered_question = session.next_question
    if not text:
        return

    if (main_symptom := _extract_main_symptom(text)) is not None:
        session.slots.main_symptom = main_symptom
    if (onset := _extract_onset(text)) is not None:
        session.slots.onset = onset
    if (severity := _extract_severity(text)) is not None:
        session.slots.severity = severity
    if (trend := _extract_trend(text)) is not None:
        session.slots.trend = trend

    associated = [
        symptom
        for symptom in _extract_terms(text, ASSOCIATED_SYMPTOM_MARKERS)
        if symptom != session.slots.main_symptom
    ]
    if associated:
        session.slots.associated_symptoms = associated
        _mark_resolved(session, "associated_symptoms")
    mentioned_risk_factors = _extract_terms(text, RISK_FACTOR_MARKERS)
    risk_factors = _extract_positive_terms(text, RISK_FACTOR_MARKERS)
    if risk_factors:
        session.slots.risk_factors = risk_factors
        _mark_resolved(session, "risk_factors")
    elif mentioned_risk_factors:
        _mark_resolved(session, "risk_factors")
        if "risk_factors" not in session.asked_ids:
            session.asked_ids.append("risk_factors")

    if answered_question is None:
        return

    question_id = answered_question.id
    if _contains_unknown(text):
        if question_id in {"associated_symptoms", "risk_factors"}:
            value = getattr(session.slots, question_id)
            if value:
                _mark_resolved(session, question_id)
            else:
                _mark_unresolved(session, question_id)
        return

    if question_id == "main_symptom" and session.slots.main_symptom is None:
        session.slots.main_symptom = text
    elif question_id == "onset" and session.slots.onset is None:
        session.slots.onset = text
    elif question_id == "associated_symptoms" and not session.slots.associated_symptoms:
        _mark_resolved(session, question_id)
        if not any(marker in text for marker in ("没有", "无", "否认")):
            session.slots.associated_symptoms = [text]
    elif question_id == "trend" and session.slots.trend is None:
        session.slots.trend = text
    elif question_id == "risk_factors" and not session.slots.risk_factors:
        _mark_resolved(session, question_id)
        if not any(marker in text for marker in ("没有", "无", "否认")):
            session.slots.risk_factors = [text]


def _missing_information(session: TriageSession) -> list[str]:
    missing: list[str] = []
    for question in QUESTION_CATALOG:
        value = getattr(session.slots, question.id)
        if value is None:
            missing.append(SLOT_LABELS[question.id])
        elif isinstance(value, list) and not value:
            if (
                question.id not in session.asked_ids
                or question.id in session.unresolved_ids
            ):
                missing.append(SLOT_LABELS[question.id])
    return missing


def _has_conflict(slots: TriageSlots) -> bool:
    return bool(slots.trend and "冲突" in slots.trend)


def _is_short_duration(onset: str | None) -> bool:
    if onset is None:
        return False
    return any(marker in onset for marker in SHORT_ONSET_MARKERS)


def _visit_summary(slots: TriageSlots) -> str:
    parts = []
    safe_main_symptom = (
        _extract_main_symptom(slots.main_symptom) if slots.main_symptom else None
    )
    safe_onset = _extract_onset(slots.onset) if slots.onset else None
    safe_associated = [
        symptom
        for symptom in slots.associated_symptoms
        if symptom in ASSOCIATED_SYMPTOM_MARKERS
    ]
    safe_risk_factors = [
        factor for factor in slots.risk_factors if factor in RISK_FACTOR_MARKERS
    ]
    if safe_main_symptom:
        parts.append(f"主要症状：{safe_main_symptom}")
    if safe_onset:
        parts.append(f"开始时间：{safe_onset}")
    if slots.severity is not None:
        parts.append(f"严重程度：{slots.severity}/10")
    if safe_associated:
        parts.append(f"伴随症状：{'、'.join(safe_associated)}")
    if slots.trend in SAFE_TREND_VALUES:
        parts.append(f"变化趋势：{slots.trend}")
    if safe_risk_factors:
        parts.append(f"风险背景：{'、'.join(safe_risk_factors)}")
    return "；".join(parts) or "当前可用症状信息有限"


def _build_result(
    level: UrgencyLevel,
    session: TriageSession,
) -> TriageResult:
    missing = _missing_information(session)
    common_escalations = ["症状明显加重", "出现呼吸困难、意识异常或无法控制的出血"]
    settings = {
        UrgencyLevel.EMERGENCY: {
            "time_window": "请立即联系急救服务或前往急诊",
            "department": ["急诊"],
            "reasoning_summary": ["输入命中固定高风险表现"],
            "escalation_signs": [],
        },
        UrgencyLevel.URGENT: {
            "time_window": "建议今天尽快就医",
            "department": ["综合内科", "急诊"],
            "reasoning_summary": ["严重程度较高或症状持续加重"],
            "escalation_signs": common_escalations,
        },
        UrgencyLevel.ROUTINE: {
            "time_window": "建议近期预约门诊",
            "department": ["综合内科"],
            "reasoning_summary": ["信息较完整，且未命中固定红旗规则"],
            "escalation_signs": common_escalations,
        },
        UrgencyLevel.SELF_MONITOR: {
            "time_window": "可先观察24小时并记录变化",
            "department": ["综合内科"],
            "reasoning_summary": ["症状轻微、出现时间短且正在改善"],
            "escalation_signs": common_escalations,
        },
        UrgencyLevel.INSUFFICIENT: {
            "time_window": "信息不足，请咨询人工医疗渠道",
            "department": ["综合内科"],
            "reasoning_summary": ["现有信息不足或相互冲突，无法可靠分层"],
            "escalation_signs": common_escalations,
        },
    }
    values = settings[level]
    reasoning_summary = list(values["reasoning_summary"])
    if level is UrgencyLevel.ROUTINE and session.slots.risk_factors:
        reasoning_summary = ["存在特殊风险背景，采取更保守的近期就医建议"]
    return TriageResult(
        urgency_level=level,
        time_window=values["time_window"],
        department=values["department"],
        reasoning_summary=reasoning_summary,
        unknowns=missing,
        escalation_signs=values["escalation_signs"],
        visit_summary=_visit_summary(session.slots),
    )


def _complete(
    session: TriageSession,
    level: UrgencyLevel,
) -> TriageSession:
    result = validate_result(_build_result(level, session))
    session.completed = True
    session.next_question = None
    session.result = result
    return session


def advance(session: TriageSession, user_text: str) -> TriageSession:
    """Merge one turn, check red flags, then ask once or return a safe result."""
    updated = session.model_copy(deep=True)
    _remember_evidence(updated, user_text)

    if updated.completed:
        red_flags = _screen_for_red_flags(updated)
        if not red_flags or (
            updated.result is not None
            and updated.result.urgency_level is UrgencyLevel.EMERGENCY
        ):
            return updated
        return _complete(
            updated,
            UrgencyLevel.EMERGENCY,
        )

    _merge_answer(updated, user_text)

    red_flags = _screen_for_red_flags(updated)
    if red_flags:
        return _complete(
            updated,
            UrgencyLevel.EMERGENCY,
        )

    if _has_conflict(updated.slots):
        return _complete(updated, UrgencyLevel.INSUFFICIENT)
    if updated.slots.severity is not None and updated.slots.severity >= 7:
        return _complete(updated, UrgencyLevel.URGENT)
    if updated.slots.trend == "持续加重":
        return _complete(updated, UrgencyLevel.URGENT)

    next_question = select_next_question(updated.slots, updated.asked_ids)
    if next_question is not None:
        if updated.question_count >= MAX_QUESTIONS:
            return _complete(updated, UrgencyLevel.INSUFFICIENT)
        updated.next_question = next_question
        updated.asked_ids.append(next_question.id)
        updated.question_count += 1
        return updated

    if _missing_information(updated):
        return _complete(updated, UrgencyLevel.INSUFFICIENT)

    if (
        not updated.slots.risk_factors
        and
        updated.slots.severity is not None
        and updated.slots.severity <= 3
        and updated.slots.trend == "改善中"
        and _is_short_duration(updated.slots.onset)
    ):
        return _complete(updated, UrgencyLevel.SELF_MONITOR)

    return _complete(updated, UrgencyLevel.ROUTINE)
