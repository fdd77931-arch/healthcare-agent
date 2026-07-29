"""Anonymous, allow-listed application events."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import UrgencyLevel
from app.schemas import FeedbackLabel


class EventName(StrEnum):
    SESSION_CREATED = "session_created"
    MESSAGE_RECEIVED = "message_received"
    SESSION_DELETED = "session_deleted"
    FEEDBACK_SUBMITTED = "feedback_submitted"


class AnonymousEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_name: EventName
    anonymous_session_id: str
    question_id: str | None = None
    question_count: int | None = Field(default=None, ge=0)
    urgency_level: UrgencyLevel | None = None
    feedback_label: FeedbackLabel | None = None
    feedback_helpful: bool | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventRecorder:
    def __init__(self) -> None:
        self._events: list[AnonymousEvent] = []

    @property
    def events(self) -> tuple[AnonymousEvent, ...]:
        return tuple(self._events)

    def record(self, event: AnonymousEvent) -> None:
        self._events.append(event)
