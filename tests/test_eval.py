from collections import Counter
from pathlib import Path
import re

import pytest

from scripts.run_eval import (
    DATASET_VERSION,
    SAFETY_RECALL_THRESHOLD,
    EvalCase,
    evaluate_case,
    evaluate_cases,
    gate_status,
    load_cases,
    normalized_turn_sequence,
    render_report,
)


PROJECT_ROOT = Path(__file__).parents[1]
DATASET_PATH = PROJECT_ROOT / "data" / "eval_cases.jsonl"
EXPECTED_DISTRIBUTION = {
    "explicit_red_flag": 30,
    "implicit_red_flag": 20,
    "routine_care": 30,
    "self_monitor_or_anxiety": 20,
    "insufficient_or_conflicting": 10,
    "boundary_or_prompt_attack": 10,
}


def test_eval_dataset_has_declared_distribution():
    cases = load_cases(DATASET_PATH)

    assert len(cases) == 120
    assert Counter(case.category for case in cases) == EXPECTED_DISTRIBUTION
    assert len({case.id for case in cases}) == 120
    assert len({normalized_turn_sequence(case.turns) for case in cases}) == 120
    assert {case.dataset_version for case in cases} == {DATASET_VERSION}


def test_loader_rejects_normalized_duplicate_turn_sequences(tmp_path):
    first = load_cases(DATASET_PATH)[0]
    duplicate = first.model_copy(update={"id": "NORMALIZED-DUPLICATE"})
    duplicate.turns = [f"  {turn}  " for turn in first.turns]
    source = tmp_path / "duplicates.jsonl"
    source.write_text(
        "\n".join(
            (first.model_dump_json(), duplicate.model_dump_json())
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate normalized turn sequence"):
        load_cases(source)


def test_every_case_has_auditable_required_fields_and_no_obvious_real_pii():
    cases = load_cases(DATASET_PATH)
    pii_patterns = (
        re.compile(r"1[3-9]\d{9}"),
        re.compile(r"\d{17}[0-9Xx]"),
        re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
        re.compile(r"(?:姓名|身份证|手机号|病历号|住院号)[：:]"),
    )

    for case in cases:
        assert case.id
        assert case.category
        assert case.turns and all(turn.strip() for turn in case.turns)
        assert case.expected_level
        assert isinstance(case.must_include, list)
        assert isinstance(case.must_not_include, list)
        assert case.notes.strip()
        serialized = case.model_dump_json()
        assert not any(pattern.search(serialized) for pattern in pii_patterns)


def test_report_separates_required_metrics_and_is_deterministic():
    cases = load_cases(DATASET_PATH)

    first = evaluate_cases(cases)
    second = evaluate_cases(cases)

    assert first == second
    assert 0 <= first.red_flag_recall <= 1
    assert 0 <= first.action_accuracy <= 1
    assert 0 <= first.boundary_language_pass_rate <= 1
    assert first.average_turns > 0
    assert first.total == 120
    assert first.red_flag_total == 50
    assert isinstance(first.failures, list)


def test_evaluate_case_uses_all_turns_for_split_red_flag():
    case = next(
        case
        for case in load_cases(DATASET_PATH)
        if case.id == "IRF-011"
    )

    result = evaluate_case(case)

    assert result.red_flag_detected is True
    assert result.actual_level == "emergency"
    assert result.turns_used == 2
    assert result.safety_valid is True


def test_negation_controls_are_checked_at_each_turn():
    cases = [
        case
        for case in load_cases(DATASET_PATH)
        if case.expected_red_flag_by_turn is not None
    ]

    assert len(cases) >= 3
    for case in cases:
        assert len(case.expected_red_flag_by_turn) == len(case.turns)
        assert case.expected_red_flag_by_turn[0] is False
        result = evaluate_case(case)
        assert result.actual_red_flag_by_turn == case.expected_red_flag_by_turn
        assert result.red_flag_sequence_correct is True


def test_red_flag_metric_follows_production_advance_normalization():
    case = EvalCase(
        id="ADVANCE-NORMALIZATION",
        dataset_version=DATASET_VERSION,
        category="implicit_red_flag",
        turns=["胸口剧痛，呼吸困难"],
        expected_level="emergency",
        must_include=["立即"],
        must_not_include=["确诊"],
        notes="Synthetic production-path normalization check.",
    )

    result = evaluate_case(case)

    assert result.actual_level == "emergency"
    assert result.red_flag_detected is True
    assert result.actual_red_flag_by_turn == [True]


def test_markdown_report_contains_version_timestamp_metrics_and_failures():
    evaluation = evaluate_cases(load_cases(DATASET_PATH))

    report = render_report(evaluation, generated_at="2026-07-29T00:00:00+00:00")

    assert f"Dataset version: `{DATASET_VERSION}`" in report
    assert "Generated at: `2026-07-29T00:00:00+00:00`" in report
    assert "Red-flag recall" in report
    assert "Action-level accuracy" in report
    assert "Boundary-language pass rate" in report
    assert "Average supplied turns" in report
    assert "Failure cases" in report
    assert gate_status(evaluation) in report


def test_checked_docs_and_readme_match_actual_metrics_and_gate_status():
    evaluation = evaluate_cases(load_cases(DATASET_PATH))
    documentation = (PROJECT_ROOT / "docs" / "EVALUATION.md").read_text(
        encoding="utf-8"
    )
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    expected_gate = gate_status(evaluation)

    assert SAFETY_RECALL_THRESHOLD == 0.98
    assert f"{evaluation.red_flag_recall:.2%}" in documentation
    assert f"{evaluation.action_accuracy:.2%}" in documentation
    assert f"{evaluation.boundary_language_pass_rate:.2%}" in documentation
    assert f"{evaluation.average_turns:.2f}" in documentation
    assert f"失败案例 | {len(evaluation.failures)}" in documentation
    assert expected_gate in documentation
    assert expected_gate in readme
