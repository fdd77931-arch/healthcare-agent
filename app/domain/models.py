from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class UrgencyLevel(StrEnum):
    EMERGENCY = "emergency"
    URGENT = "urgent"
    ROUTINE = "routine"
    SELF_MONITOR = "self_monitor"
    INSUFFICIENT = "insufficient"


class TriageSlots(BaseModel):
    main_symptom: str | None = None
    onset: str | None = None
    trend: str | None = None
    severity: int | None = Field(default=None, ge=0, le=10)
    associated_symptoms: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)


class RedFlagMatch(BaseModel):
    rule_id: str
    level: UrgencyLevel
    evidence: str
    action: str


class TriageQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    prompt: str
    rationale: str
    answer_type: str

    @property
    def allowed_answer_types(self) -> tuple[str, ...]:
        return (self.answer_type,)


DEFAULT_DISCLAIMER = "本结果仅用于行动分层，不构成诊断或治疗建议。"


class TriageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    urgency_level: UrgencyLevel
    time_window: str
    department: list[str]
    reasoning_summary: list[str]
    unknowns: list[str]
    escalation_signs: list[str]
    visit_summary: str
    disclaimer: str = DEFAULT_DISCLAIMER
