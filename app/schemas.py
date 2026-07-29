"""Explicit public request and response schemas for the HTTP API."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.models import UrgencyLevel


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionMessageRequest(ApiModel):
    message: str = Field(min_length=1, max_length=2_000)


class PublicQuestion(ApiModel):
    id: str
    prompt: str
    answer_type: str


class PublicTriageResult(ApiModel):
    urgency_level: UrgencyLevel
    time_window: str
    department: list[str]
    reasoning_summary: list[str]
    unknowns: list[str]
    escalation_signs: list[str]
    visit_summary: str
    disclaimer: str


class SessionResponse(ApiModel):
    session_id: str
    status: Literal["active", "completed"]
    question: PublicQuestion | None
    result: PublicTriageResult | None


class FeedbackLabel(StrEnum):
    HELPFUL = "helpful"
    DIAGNOSTIC_LANGUAGE = "diagnostic_language"
    TREATMENT_LANGUAGE = "treatment_language"
    UNCLEAR_QUESTION = "unclear_question"
    MISSING_OPTION = "missing_option"
    OTHER_SAFETY_CONCERN = "other_safety_concern"


class FeedbackRequest(ApiModel):
    helpful: bool
    label: FeedbackLabel

    @model_validator(mode="after")
    def feedback_label_matches_helpfulness(self) -> "FeedbackRequest":
        is_helpful_label = self.label is FeedbackLabel.HELPFUL
        if self.helpful is not is_helpful_label:
            raise ValueError("Feedback label does not match helpfulness")
        return self


class FeedbackResponse(ApiModel):
    accepted: Literal[True] = True
