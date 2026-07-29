"""Privacy-aware HTTP routes for the triage lifecycle."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status

from app.domain.models import TriageResult, UrgencyLevel
from app.domain.triage import TriageSession, advance
from app.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    PublicQuestion,
    PublicTriageResult,
    SessionMessageRequest,
    SessionResponse,
)
from app.services.analytics import AnonymousEvent, EventName, EventRecorder
from app.services.llm import SlotParser
from app.services.sessions import SessionStore


PUBLIC_REASONING: dict[UrgencyLevel, tuple[str, ...]] = {
    UrgencyLevel.EMERGENCY: ("固定安全规则提示存在需要立即处理的高风险表现",),
    UrgencyLevel.URGENT: ("现有信息提示需要在今天尽快就医",),
    UrgencyLevel.ROUTINE: ("现有信息未触发固定高风险规则，可安排近期门诊",),
    UrgencyLevel.SELF_MONITOR: ("现有信息支持短期观察并留意变化",),
    UrgencyLevel.INSUFFICIENT: ("现有信息不足或存在冲突，需要人工医疗咨询",),
}


def _public_result(result: TriageResult) -> PublicTriageResult:
    visit_summary = (
        "已识别需要立即处理的高风险表现，请优先按行动建议处理。"
        if result.urgency_level is UrgencyLevel.EMERGENCY
        else result.visit_summary
    )
    return PublicTriageResult(
        urgency_level=result.urgency_level,
        time_window=result.time_window,
        department=list(result.department),
        reasoning_summary=list(PUBLIC_REASONING[result.urgency_level]),
        unknowns=list(result.unknowns),
        escalation_signs=list(result.escalation_signs),
        visit_summary=visit_summary,
        disclaimer=result.disclaimer,
    )


def _session_response(session: TriageSession) -> SessionResponse:
    question = session.next_question
    return SessionResponse(
        session_id=session.session_id,
        status="completed" if session.completed else "active",
        question=(
            PublicQuestion(
                id=question.id,
                prompt=question.prompt,
                answer_type=question.answer_type,
            )
            if question is not None
            else None
        ),
        result=_public_result(session.result) if session.result is not None else None,
    )


def _event_for(session: TriageSession, event_name: EventName) -> AnonymousEvent:
    return AnonymousEvent(
        event_name=event_name,
        anonymous_session_id=session.session_id,
        question_id=(
            session.next_question.id if session.next_question is not None else None
        ),
        question_count=session.question_count,
        urgency_level=(
            session.result.urgency_level if session.result is not None else None
        ),
    )


def _advance_with_parser(
    session: TriageSession,
    message: str,
    slot_parser: SlotParser,
) -> TriageSession:
    parsed = session.model_copy(deep=True)
    parsed.slots = slot_parser.parse(message, parsed.slots).model_copy(deep=True)
    return advance(parsed, message)


def create_api_router(
    sessions: SessionStore,
    analytics: EventRecorder,
    slot_parser: SlotParser,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post(
        "/sessions",
        response_model=SessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_session(payload: SessionMessageRequest) -> SessionResponse:
        session = _advance_with_parser(
            TriageSession(),
            payload.message,
            slot_parser,
        )
        stored = sessions.create(session)
        analytics.record(_event_for(stored, EventName.SESSION_CREATED))
        return _session_response(stored)

    @router.post(
        "/sessions/{session_id}/messages",
        response_model=SessionResponse,
    )
    def add_message(
        session_id: str,
        payload: SessionMessageRequest,
    ) -> SessionResponse:
        stored = sessions.update(
            session_id,
            lambda session: _advance_with_parser(
                session,
                payload.message,
                slot_parser,
            ),
        )
        if stored is None:
            raise HTTPException(status_code=404, detail="Session not found")
        analytics.record(_event_for(stored, EventName.MESSAGE_RECEIVED))
        return _session_response(stored)

    @router.delete(
        "/sessions/{session_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    def delete_session(session_id: str) -> Response:
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        sessions.delete(session_id)
        analytics.record(_event_for(session, EventName.SESSION_DELETED))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post(
        "/feedback",
        response_model=FeedbackResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def submit_feedback(payload: FeedbackRequest) -> FeedbackResponse:
        analytics.record(
            AnonymousEvent(
                event_name=EventName.FEEDBACK_SUBMITTED,
                anonymous_session_id=uuid4().hex,
                feedback_label=payload.label,
                feedback_helpful=payload.helpful,
            )
        )
        return FeedbackResponse()

    return router
