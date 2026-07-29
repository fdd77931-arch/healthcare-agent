import pytest

from app.domain.models import TriageSlots, UrgencyLevel
from app.domain.red_flags import detect_red_flags


def test_detects_chest_pain_with_breathing_difficulty():
    matches = detect_red_flags("胸口剧烈疼痛，而且喘不上气", TriageSlots())

    assert matches[0].level is UrgencyLevel.EMERGENCY
    assert matches[0].rule_id == "cardiopulmonary_emergency"


def test_does_not_trigger_negated_breathing_difficulty():
    matches = detect_red_flags("有一点胸闷，但没有呼吸困难，也没有出汗", TriageSlots())

    assert matches == []


@pytest.mark.parametrize(
    "text",
    [
        "胸痛，没有任何呼吸困难",
        "胸痛，没有明显呼吸困难",
        "胸痛，否认有呼吸困难",
        "胸痛，否认有任何呼吸困难",
    ],
)
def test_does_not_trigger_breathing_difficulty_negated_with_local_modifier(text: str):
    assert detect_red_flags(text, TriageSlots()) == []


def test_detects_later_breathing_difficulty_after_an_earlier_negation():
    matches = detect_red_flags("开始没有呼吸困难，后来胸痛加重并出现呼吸困难", TriageSlots())

    assert matches[0].rule_id == "cardiopulmonary_emergency"


def test_detects_self_harm_language():
    matches = detect_red_flags("我不想活了，想结束这一切", TriageSlots())

    assert matches[0].rule_id == "self_harm_emergency"


@pytest.mark.parametrize(
    ("text", "rule_id"),
    [
        ("胸口剧烈疼痛，呼吸困难", "cardiopulmonary_emergency"),
        ("突然一侧手脚无力，说话含糊", "stroke_emergency"),
        ("吃完花生后全身起风团，喉咙发紧", "severe_allergy_emergency"),
        ("伤口一直喷血，怎么也止不住", "major_bleeding_emergency"),
        ("刚才突然失去意识，还全身抽搐", "consciousness_or_seizure_emergency"),
        ("我想自杀，不想继续活下去了", "self_harm_emergency"),
    ],
)
def test_detects_each_emergency_red_flag(text: str, rule_id: str):
    matches = detect_red_flags(text, TriageSlots())

    assert matches[0].level is UrgencyLevel.EMERGENCY
    assert matches[0].rule_id == rule_id
    assert matches[0].evidence in text


@pytest.mark.parametrize(
    "text",
    [
        "没有呼吸困难，只是有点胸闷",
        "没有一侧无力，说话也很清楚",
        "没有喉咙发紧，也没有全身风团",
        "伤口没有出血，只是轻微擦伤",
        "没有失去意识，也没有抽搐",
        "我没有自杀的想法，只是最近压力很大",
    ],
)
def test_does_not_trigger_negated_red_flag_language(text: str):
    assert detect_red_flags(text, TriageSlots()) == []


@pytest.mark.parametrize("text", ["咳嗽止不住", "打嗝止不住"])
def test_does_not_treat_non_bleeding_symptoms_that_do_not_stop_as_major_bleeding(text: str):
    assert detect_red_flags(text, TriageSlots()) == []


def test_does_not_use_a_negated_bleeding_phrase_as_stop_phrase_context():
    assert detect_red_flags("没有出血，咳嗽止不住", TriageSlots()) == []


def test_detects_uncontrolled_bleeding_described_with_stop_phrase():
    matches = detect_red_flags("伤口一直出血，怎么都止不住", TriageSlots())

    assert matches[0].rule_id == "major_bleeding_emergency"
