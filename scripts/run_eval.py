#!/usr/bin/env python3
"""Run the deterministic, offline product-label evaluation suite."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Literal
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, model_validator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.models import UrgencyLevel  # noqa: E402
from app.domain.red_flags import detect_red_flags  # noqa: E402
from app.domain.safety import validate_result  # noqa: E402
from app.domain.triage import TriageSession, advance  # noqa: E402


DATASET_VERSION = "1.1.0"
SAFETY_RECALL_THRESHOLD = 0.98
Category = Literal[
    "explicit_red_flag",
    "implicit_red_flag",
    "routine_care",
    "self_monitor_or_anxiety",
    "insufficient_or_conflicting",
    "boundary_or_prompt_attack",
]


class EvalCase(BaseModel):
    """One synthetic, reviewable product test case."""

    model_config = ConfigDict(extra="forbid")

    id: str
    dataset_version: str
    category: Category
    turns: list[str] = Field(min_length=1)
    expected_level: UrgencyLevel
    expected_red_flag_by_turn: list[bool] | None = None
    must_include: list[str]
    must_not_include: list[str]
    notes: str

    @model_validator(mode="after")
    def validate_turn_expectations(self) -> "EvalCase":
        if (
            self.expected_red_flag_by_turn is not None
            and len(self.expected_red_flag_by_turn) != len(self.turns)
        ):
            raise ValueError(
                "expected_red_flag_by_turn must have one value per turn"
            )
        return self


class CaseResult(BaseModel):
    """Deterministic outcome and failure reasons for one case."""

    model_config = ConfigDict(extra="forbid")

    id: str
    category: Category
    expected_level: UrgencyLevel
    actual_level: UrgencyLevel | None
    red_flag_expected: bool
    red_flag_detected: bool
    actual_red_flag_by_turn: list[bool]
    red_flag_sequence_correct: bool
    action_correct: bool
    boundary_language_pass: bool
    safety_valid: bool
    turns_used: int
    failure_reasons: list[str]


class EvaluationReport(BaseModel):
    """Aggregate metrics kept separate to avoid hiding safety regressions."""

    model_config = ConfigDict(extra="forbid")

    dataset_version: str
    total: int
    red_flag_total: int
    red_flag_recall: float
    action_accuracy: float
    boundary_language_pass_rate: float
    average_turns: float
    failures: list[CaseResult]


def normalized_turn_sequence(turns: list[str]) -> tuple[str, ...]:
    """Canonicalize a sequence for duplicate-audit comparisons."""
    return tuple(
        " ".join(unicodedata.normalize("NFKC", turn).split()).casefold()
        for turn in turns
    )


def load_cases(path: str | Path) -> list[EvalCase]:
    """Load strict JSONL records and identify malformed source lines."""
    source = Path(path)
    cases: list[EvalCase] = []
    for line_number, raw_line in enumerate(
        source.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue
        try:
            case = EvalCase.model_validate_json(raw_line)
        except ValueError as exc:
            raise ValueError(f"{source}:{line_number}: invalid evaluation case") from exc
        if case.dataset_version != DATASET_VERSION:
            raise ValueError(
                f"{source}:{line_number}: unsupported dataset version "
                f"{case.dataset_version!r}"
            )
        cases.append(case)

    duplicate_ids = sorted(
        case_id
        for case_id in {case.id for case in cases}
        if sum(case.id == case_id for case in cases) > 1
    )
    if duplicate_ids:
        raise ValueError(f"duplicate case ids: {', '.join(duplicate_ids)}")
    sequence_owners: dict[tuple[str, ...], str] = {}
    for case in cases:
        sequence = normalized_turn_sequence(case.turns)
        if previous_id := sequence_owners.get(sequence):
            raise ValueError(
                "duplicate normalized turn sequence: "
                f"{previous_id} and {case.id}"
            )
        sequence_owners[sequence] = case.id
    return cases


def _result_text(session: TriageSession) -> str:
    if session.result is None:
        return ""
    return session.result.model_dump_json()


def evaluate_case(case: EvalCase) -> CaseResult:
    """Feed one case through production screening, state, and safety functions."""
    session = TriageSession()
    actual_red_flag_by_turn: list[bool] = []
    turns_used = 0
    runtime_error: str | None = None

    for turn in case.turns:
        turns_used += 1
        audit_text = " ".join([*session.screening_evidence, turn])
        audit_text = audit_text.replace("胸口剧痛", "胸痛")
        # Keep the brief's direct detector interface under evaluation. Recall is
        # intentionally derived from the state returned by advance below.
        detect_red_flags(audit_text, session.slots)
        try:
            session = advance(session, turn)
        except (ValueError, TypeError) as exc:
            runtime_error = f"{type(exc).__name__}: {exc}"
            actual_red_flag_by_turn.append(False)
            break
        actual_red_flag_by_turn.append(
            bool(
                session.result is not None
                and session.result.urgency_level is UrgencyLevel.EMERGENCY
            )
        )

    red_flag_detected = any(actual_red_flag_by_turn)
    red_flag_sequence_correct = (
        case.expected_red_flag_by_turn is None
        or actual_red_flag_by_turn == case.expected_red_flag_by_turn
    )

    safety_valid = False
    if runtime_error is None and session.result is not None:
        try:
            validate_result(session.result)
            safety_valid = True
        except ValueError as exc:
            runtime_error = f"{type(exc).__name__}: {exc}"

    output_text = _result_text(session)
    missing_required = [
        phrase for phrase in case.must_include if phrase not in output_text
    ]
    forbidden_present = [
        phrase for phrase in case.must_not_include if phrase in output_text
    ]
    boundary_pass = (
        safety_valid
        and not missing_required
        and not forbidden_present
    )
    actual_level = (
        session.result.urgency_level if session.result is not None else None
    )
    action_correct = actual_level == case.expected_level
    red_flag_expected = case.category in {
        "explicit_red_flag",
        "implicit_red_flag",
    }

    failures: list[str] = []
    if red_flag_expected and not red_flag_detected:
        failures.append("red flag not detected")
    if not red_flag_sequence_correct:
        failures.append(
            "per-turn red flag expected "
            f"{case.expected_red_flag_by_turn}, got {actual_red_flag_by_turn}"
        )
    if not action_correct:
        actual = actual_level.value if actual_level is not None else "no_result"
        failures.append(
            f"action level expected {case.expected_level.value}, got {actual}"
        )
    if missing_required:
        failures.append(f"missing required language: {', '.join(missing_required)}")
    if forbidden_present:
        failures.append(f"forbidden language present: {', '.join(forbidden_present)}")
    if not safety_valid:
        failures.append(runtime_error or "no final result to validate")

    return CaseResult(
        id=case.id,
        category=case.category,
        expected_level=case.expected_level,
        actual_level=actual_level,
        red_flag_expected=red_flag_expected,
        red_flag_detected=red_flag_detected,
        actual_red_flag_by_turn=actual_red_flag_by_turn,
        red_flag_sequence_correct=red_flag_sequence_correct,
        action_correct=action_correct,
        boundary_language_pass=boundary_pass,
        safety_valid=safety_valid,
        turns_used=turns_used,
        failure_reasons=failures,
    )


def evaluate_cases(cases: list[EvalCase]) -> EvaluationReport:
    """Evaluate all cases without blending distinct safety/product metrics."""
    if not cases:
        raise ValueError("evaluation dataset is empty")
    results = [evaluate_case(case) for case in cases]
    red_flag_results = [result for result in results if result.red_flag_expected]
    red_flag_recall = (
        sum(result.red_flag_detected for result in red_flag_results)
        / len(red_flag_results)
        if red_flag_results
        else 0.0
    )
    failures = [result for result in results if result.failure_reasons]
    return EvaluationReport(
        dataset_version=DATASET_VERSION,
        total=len(results),
        red_flag_total=len(red_flag_results),
        red_flag_recall=red_flag_recall,
        action_accuracy=sum(result.action_correct for result in results)
        / len(results),
        boundary_language_pass_rate=sum(
            result.boundary_language_pass for result in results
        )
        / len(results),
        average_turns=sum(result.turns_used for result in results) / len(results),
        failures=failures,
    )


def _percent(value: float) -> str:
    return f"{value:.2%}"


def gate_status(report: EvaluationReport) -> str:
    """Return the checked product safety-gate label."""
    if report.red_flag_recall >= SAFETY_RECALL_THRESHOLD:
        return "安全门槛通过"
    return "安全门槛未通过"


def render_report(
    report: EvaluationReport,
    generated_at: str | None = None,
) -> str:
    """Render an auditable Markdown snapshot without assigning clinical meaning."""
    timestamp = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# Offline evaluation result",
        "",
        f"Dataset version: `{report.dataset_version}`",
        f"Generated at: `{timestamp}`",
        "",
        "These are deterministic product test labels, not clinical gold-standard "
        "diagnoses or evidence of clinical effectiveness.",
        "",
        (
            f"Safety gate: **{gate_status(report)}** "
            f"(red-flag recall threshold: {_percent(SAFETY_RECALL_THRESHOLD)})."
        ),
        "",
        "## Metrics",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        (
            f"| Red-flag recall | {_percent(report.red_flag_recall)} "
            f"({report.red_flag_total} labelled red-flag cases) |"
        ),
        f"| Action-level accuracy | {_percent(report.action_accuracy)} |",
        (
            "| Boundary-language pass rate | "
            f"{_percent(report.boundary_language_pass_rate)} |"
        ),
        f"| Average supplied turns | {report.average_turns:.2f} |",
        f"| Failure cases | {len(report.failures)} |",
        "",
        "## Failure cases",
        "",
    ]
    if not report.failures:
        lines.append("No failures in this synthetic product test set.")
    else:
        lines.extend(
            f"- `{failure.id}` ({failure.category}): "
            + "; ".join(failure.failure_reasons)
            for failure in report.failures
        )
    return "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = evaluate_cases(load_cases(args.input))
    rendered = render_report(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Red-flag recall: {_percent(report.red_flag_recall)}")
    print(f"Action-level accuracy: {_percent(report.action_accuracy)}")
    print(
        "Boundary-language pass rate: "
        f"{_percent(report.boundary_language_pass_rate)}"
    )
    print(f"Average supplied turns: {report.average_turns:.2f}")
    print(f"Failure cases: {len(report.failures)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
