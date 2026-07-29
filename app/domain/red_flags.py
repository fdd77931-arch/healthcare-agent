"""Deterministic, high-sensitivity emergency red-flag screening."""

from collections.abc import Callable

from app.domain.models import RedFlagMatch, TriageSlots, UrgencyLevel


EMERGENCY_ACTION = "请立即联系急救服务或前往急诊。"
SELF_HARM_ACTION = "请立即联系急救服务、可信任的人或当地危机支持。"
NEGATION_PREFIXES = ("并没有", "没有", "否认", "未见", "不是", "无", "未")
NEGATION_FILLERS = ("任何", "明显", "有", "有任何")
BLEEDING_CONTEXT_PHRASES = ("出血", "流血", "血")
BLEEDING_COMPOUND_PHRASES = ("大量出血", "出血", "流血")


def _is_negated(text: str, position: int) -> bool:
    """Recognize a negator and one bounded common filler sequence before a phrase."""
    prefix_window = text[max(0, position - 6) : position]
    return any(
        prefix_window.endswith(negator + filler)
        for negator in NEGATION_PREFIXES
        for filler in ("", *NEGATION_FILLERS)
    )


def _all_positive_phrase_positions(text: str, phrase: str) -> list[int]:
    positions: list[int] = []
    position = text.find(phrase)
    while position >= 0:
        if not _is_negated(text, position):
            positions.append(position)
        position = text.find(phrase, position + len(phrase))
    return positions


def _is_negated_bleeding_context(text: str, position: int) -> bool:
    """Treat an embedded bleeding substring as negated with its containing phrase."""
    context_start = position
    for compound_phrase in BLEEDING_COMPOUND_PHRASES:
        compound_start = text.rfind(
            compound_phrase,
            max(0, position - len(compound_phrase) + 1),
            position + 1,
        )
        if compound_start >= 0 and compound_start <= position < compound_start + len(compound_phrase):
            context_start = min(context_start, compound_start)
    return _is_negated(text, context_start)


def _first_positive_phrase(text: str, phrases: tuple[str, ...]) -> tuple[int, str] | None:
    candidates: list[tuple[int, str]] = []
    for phrase in phrases:
        position = text.find(phrase)
        while position >= 0:
            if not _is_negated(text, position):
                candidates.append((position, phrase))
            position = text.find(phrase, position + len(phrase))

    return min(candidates, default=None)


def _evidence_for(text: str, *phrases: tuple[int, str]) -> str:
    start = min(position for position, _ in phrases)
    end = max(position + len(phrase) for position, phrase in phrases)
    return text[start:end]


def _match_required_phrases(
    text: str,
    groups: tuple[tuple[str, ...], ...],
    rule_id: str,
    action: str = EMERGENCY_ACTION,
) -> RedFlagMatch | None:
    matches = [_first_positive_phrase(text, phrases) for phrases in groups]
    if any(match is None for match in matches):
        return None

    phrase_matches = tuple(match for match in matches if match is not None)
    return RedFlagMatch(
        rule_id=rule_id,
        level=UrgencyLevel.EMERGENCY,
        evidence=_evidence_for(text, *phrase_matches),
        action=action,
    )


def _cardiopulmonary_emergency(text: str) -> RedFlagMatch | None:
    return _match_required_phrases(
        text,
        (("胸口剧烈疼痛", "胸痛", "胸口疼"), ("呼吸困难", "喘不上气", "气短")),
        "cardiopulmonary_emergency",
    )


def _stroke_emergency(text: str) -> RedFlagMatch | None:
    return _match_required_phrases(
        text,
        (("一侧手脚无力", "一侧无力", "半边无力", "口角歪"), ("说话含糊", "说不清话", "言语不清")),
        "stroke_emergency",
    )


def _severe_allergy_emergency(text: str) -> RedFlagMatch | None:
    return _match_required_phrases(
        text,
        (("喉咙发紧", "喉头紧", "嘴唇肿", "舌头肿"), ("全身起风团", "全身风团", "全身荨麻疹")),
        "severe_allergy_emergency",
    )


def _major_bleeding_emergency(text: str) -> RedFlagMatch | None:
    direct_match = _first_positive_phrase(text, ("喷血", "大量出血", "出血不止"))
    if direct_match is not None:
        return RedFlagMatch(
            rule_id="major_bleeding_emergency",
            level=UrgencyLevel.EMERGENCY,
            evidence=_evidence_for(text, direct_match),
            action=EMERGENCY_ACTION,
        )

    for stop_position in _all_positive_phrase_positions(text, "止不住"):
        context_start = max(0, stop_position - 8)
        for context_phrase in BLEEDING_CONTEXT_PHRASES:
            context_position = text.rfind(context_phrase, context_start, stop_position)
            if context_position >= 0 and not _is_negated_bleeding_context(text, context_position):
                return RedFlagMatch(
                    rule_id="major_bleeding_emergency",
                    level=UrgencyLevel.EMERGENCY,
                    evidence=_evidence_for(
                        text,
                        (context_position, context_phrase),
                        (stop_position, "止不住"),
                    ),
                    action=EMERGENCY_ACTION,
                )
    return None


def _consciousness_or_seizure_emergency(text: str) -> RedFlagMatch | None:
    return _match_required_phrases(
        text,
        (("失去意识", "昏迷", "晕倒", "昏厥", "抽搐", "惊厥"),),
        "consciousness_or_seizure_emergency",
    )


def _self_harm_emergency(text: str) -> RedFlagMatch | None:
    return _match_required_phrases(
        text,
        (("不想活了", "结束这一切", "想自杀", "自杀", "结束生命"),),
        "self_harm_emergency",
        SELF_HARM_ACTION,
    )


RULES: tuple[Callable[[str], RedFlagMatch | None], ...] = (
    _cardiopulmonary_emergency,
    _stroke_emergency,
    _severe_allergy_emergency,
    _major_bleeding_emergency,
    _consciousness_or_seizure_emergency,
    _self_harm_emergency,
)


def detect_red_flags(text: str, slots: TriageSlots) -> list[RedFlagMatch]:
    """Return every deterministic emergency match found in the user's text."""
    del slots
    return [match for rule in RULES if (match := rule(text)) is not None]
