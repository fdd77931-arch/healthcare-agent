"""Final deterministic safety gate for structured triage output."""

import re
from collections.abc import Iterable

from app.domain.models import TriageResult, UrgencyLevel


DIAGNOSTIC_PHRASES = ("你得了", "确诊", "诊断为", "你患有", "患上")
DOSAGE_PHRASES = ("每天服用", "每次服用")
TREATMENT_PHRASES = (
    "建议口服",
    "建议服用",
    "建议吃药",
    "请服用",
    "可以服用",
    "需要服用",
)
DIAGNOSTIC_PATTERNS = (
    re.compile(r"这是[^，。；\n]{0,20}(?:病|心肌梗死)"),
)
DOSAGE_PATTERNS = (
    re.compile(
        r"(?:每天|每日|每次)[^，。；\n]{0,16}"
        r"(?:片|粒|毫克|毫升|mg|ml)",
        re.IGNORECASE,
    ),
)
EMERGENCY_DELAY_PATTERNS = (
    re.compile(r"[一二两三四五六七八九十百\d]+\s*(?:天|周)\s*后"),
)

TIME_WINDOW_MARKERS: dict[UrgencyLevel, tuple[str, ...]] = {
    UrgencyLevel.EMERGENCY: ("立即", "马上", "现在", "120", "急救"),
    UrgencyLevel.URGENT: ("今天", "当天", "尽快", "24小时", "24 小时"),
    UrgencyLevel.ROUTINE: ("预约", "门诊", "近期"),
    UrgencyLevel.SELF_MONITOR: ("观察", "监测"),
    UrgencyLevel.INSUFFICIENT: ("信息不足", "人工", "医疗渠道", "无法"),
}

CONFLICTING_TIME_MARKERS: dict[UrgencyLevel, tuple[str, ...]] = {
    UrgencyLevel.EMERGENCY: (
        "下周",
        "以后",
        "观察",
        "过几天",
        "几天后",
        "稍后",
        "明天",
        "预约",
    ),
    UrgencyLevel.URGENT: ("下周", "观察"),
    UrgencyLevel.ROUTINE: ("立即", "马上", "120", "急救"),
    UrgencyLevel.SELF_MONITOR: ("立即", "马上", "急诊", "急救", "今天就医"),
    UrgencyLevel.INSUFFICIENT: ("在家观察", "可先观察"),
}


def _all_text(result: TriageResult) -> Iterable[str]:
    for value in result.model_dump().values():
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            yield from (item for item in value if isinstance(item, str))


def validate_result(result: TriageResult) -> TriageResult:
    """Reject unsafe language or an action window inconsistent with its level."""
    output_text = "\n".join(_all_text(result))

    if any(phrase in output_text for phrase in DIAGNOSTIC_PHRASES) or any(
        pattern.search(output_text) for pattern in DIAGNOSTIC_PATTERNS
    ):
        raise ValueError("diagnostic language is not allowed")
    if any(phrase in output_text for phrase in DOSAGE_PHRASES) or any(
        pattern.search(output_text) for pattern in DOSAGE_PATTERNS
    ):
        raise ValueError("dosage language is not allowed")
    if any(phrase in output_text for phrase in TREATMENT_PHRASES):
        raise ValueError("treatment language is not allowed")

    window = result.time_window
    expected_markers = TIME_WINDOW_MARKERS[result.urgency_level]
    if not any(marker in window for marker in expected_markers):
        if result.urgency_level is UrgencyLevel.EMERGENCY:
            raise ValueError("emergency result requires an immediate time window")
        raise ValueError("time window conflicts with urgency level")

    conflicting_markers = CONFLICTING_TIME_MARKERS.get(result.urgency_level, ())
    if any(marker in window for marker in conflicting_markers):
        raise ValueError("time window conflicts with urgency level")
    if result.urgency_level is UrgencyLevel.EMERGENCY and any(
        pattern.search(window) for pattern in EMERGENCY_DELAY_PATTERNS
    ):
        raise ValueError("time window conflicts with urgency level")

    return result
