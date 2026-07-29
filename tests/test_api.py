from datetime import UTC, datetime, timedelta
from threading import Event, Thread

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.domain.models import TriageSlots
from app.domain.triage import TriageSession
from app.main import app, create_app
from app.services.analytics import AnonymousEvent
from app.services.llm import DemoSlotParser, build_slot_parser
from app.services.sessions import SessionStore


client = TestClient(app)


def test_health_endpoint_reports_demo_mode():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "demo"}


def test_session_lifecycle_does_not_return_raw_internal_state():
    raw_message = "头痛两天"

    created = client.post("/api/sessions", json={"message": raw_message})

    assert created.status_code == 201
    body = created.json()
    assert set(body) == {"session_id", "status", "question", "result"}
    assert raw_message not in created.text
    assert "screening_evidence" not in created.text
    assert "unresolved_ids" not in created.text
    session_id = body["session_id"]

    continued = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"message": "轻微，2分"},
    )
    assert continued.status_code == 200
    assert set(continued.json()) == {"session_id", "status", "question", "result"}
    assert "轻微，2分" not in continued.text
    assert "screening_evidence" not in continued.text

    deleted = client.delete(f"/api/sessions/{session_id}")
    assert deleted.status_code == 204
    assert deleted.content == b""

    missing = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"message": "继续"},
    )
    assert missing.status_code == 404


def test_completed_session_returns_only_explicit_result_schema():
    response = client.post(
        "/api/sessions",
        json={"message": "突然一侧手脚无力，说话含糊"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["question"] is None
    assert set(body["result"]) == {
        "urgency_level",
        "time_window",
        "department",
        "reasoning_summary",
        "unknowns",
        "escalation_signs",
        "visit_summary",
        "disclaimer",
    }
    assert "突然一侧手脚无力，说话含糊" not in response.text
    assert "一侧手脚无力" not in response.text
    assert "说话含糊" not in response.text
    assert "slots" not in response.text
    assert "asked_ids" not in response.text


def test_emergency_response_does_not_echo_treatment_text_from_input():
    private_client = TestClient(app, raise_server_exceptions=False)
    raw_message = "胸痛，建议服用阿司匹林，呼吸困难"

    response = private_client.post("/api/sessions", json={"message": raw_message})

    assert response.status_code == 201
    assert response.json()["result"]["urgency_level"] == "emergency"
    assert "建议服用阿司匹林" not in response.text
    assert "胸痛" not in response.text
    assert "呼吸困难" not in response.text


def test_completed_result_does_not_echo_free_form_symptom_answer():
    created = client.post("/api/sessions", json={"message": "只是有些不舒服"})
    session_id = created.json()["session_id"]
    raw_symptom = "PRIVATE-FREE-FORM-SYMPTOM"
    response = created

    for answer in [
        raw_symptom,
        "昨天开始",
        "2分",
        "没有",
        "逐渐好转",
        "没有",
    ]:
        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"message": answer},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert raw_symptom not in response.text


def test_completed_result_returns_minimized_structured_visit_summary():
    created = client.post(
        "/api/sessions",
        json={"message": "昨天开始咳嗽，2分，伴随流鼻涕，正在改善"},
    )
    session_id = created.json()["session_id"]
    response = created

    for answer in ["没有其他症状", "正在改善", "没有特殊风险"]:
        if response.json()["status"] == "completed":
            break
        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"message": answer},
        )

    summary = response.json()["result"]["visit_summary"]
    assert "主要症状：咳嗽" in summary
    assert "开始时间：昨天开始" in summary
    assert "严重程度：2/10" in summary
    assert "伴随症状：流鼻涕" in summary
    assert "变化趋势：改善中" in summary
    assert "诊断" not in summary


def test_visit_summary_does_not_echo_arbitrary_trend_or_pii_like_text():
    created = client.post("/api/sessions", json={"message": "今天头痛，2分"})
    session_id = created.json()["session_id"]
    response = created

    for answer in [
        "没有其他症状",
        "老样子，联系电话13800138000",
        "没有慢性病，也没有近期外伤",
    ]:
        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"message": answer},
        )

    summary = response.json()["result"]["visit_summary"]
    assert "13800138000" not in summary
    assert "联系电话" not in summary
    assert "老样子" not in summary


def test_feedback_accepts_only_fixed_labels():
    accepted = client.post(
        "/api/feedback",
        json={"helpful": False, "label": "diagnostic_language"},
    )
    assert accepted.status_code == 202
    assert accepted.json() == {"accepted": True}

    rejected = client.post(
        "/api/feedback",
        json={"helpful": False, "label": "raw free-form complaint"},
    )
    assert rejected.status_code == 422


def test_feedback_persists_helpfulness_and_rejects_incoherent_labels():
    feedback_app = create_app()
    feedback_client = TestClient(feedback_app)

    helpful = feedback_client.post(
        "/api/feedback",
        json={"helpful": True, "label": "helpful"},
    )
    needs_improvement = feedback_client.post(
        "/api/feedback",
        json={"helpful": False, "label": "unclear_question"},
    )
    incoherent_positive = feedback_client.post(
        "/api/feedback",
        json={"helpful": True, "label": "unclear_question"},
    )
    incoherent_negative = feedback_client.post(
        "/api/feedback",
        json={"helpful": False, "label": "helpful"},
    )

    assert helpful.status_code == 202
    assert needs_improvement.status_code == 202
    assert incoherent_positive.status_code == 422
    assert incoherent_negative.status_code == 422
    events = feedback_app.state.analytics.events
    assert events[-2].feedback_helpful is True
    assert events[-2].feedback_label == "helpful"
    assert events[-1].feedback_helpful is False
    assert events[-1].feedback_label == "unclear_question"


def test_validation_errors_do_not_echo_rejected_health_text():
    raw_message = "PRIVATE-SYMPTOM-" * 200

    response = client.post("/api/sessions", json={"message": raw_message})

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request payload"}
    assert raw_message not in response.text


def test_session_store_expires_and_purges_sessions_after_default_ttl():
    now = [datetime(2026, 7, 29, tzinfo=UTC)]
    store = SessionStore(clock=lambda: now[0])
    session = TriageSession(session_id="anonymous-session")
    other = TriageSession(session_id="other-anonymous-session")

    created = store.create(session)
    store.create(other)

    assert created == session
    assert created is not session
    assert store.get(session.session_id) == session

    now[0] += timedelta(minutes=30)

    assert store.delete(session.session_id) is False
    assert store.purge_expired() == 1
    assert store.get(other.session_id) is None


def test_session_store_save_refreshes_ttl_and_delete_reports_presence():
    now = [datetime(2026, 7, 29, tzinfo=UTC)]
    store = SessionStore(clock=lambda: now[0])
    session = store.create(TriageSession(session_id="anonymous-session"))
    now[0] += timedelta(minutes=20)
    session.question_count = 1

    saved = store.save(session)
    now[0] += timedelta(minutes=11)

    assert saved is not None
    assert saved is not session
    assert store.get(session.session_id).question_count == 1
    assert store.delete(session.session_id) is True
    assert store.delete(session.session_id) is False


def test_stale_save_cannot_resurrect_a_deleted_session():
    store = SessionStore()
    stale = store.create(TriageSession(session_id="anonymous-session"))

    assert store.delete(stale.session_id) is True

    assert store.save(stale) is None
    assert store.get(stale.session_id) is None


def test_delete_waits_for_atomic_update_and_session_stays_deleted():
    store = SessionStore()
    store.create(TriageSession(session_id="anonymous-session"))
    update_started = Event()
    release_update = Event()
    delete_started = Event()
    outcomes = {}

    def updater(session):
        update_started.set()
        assert release_update.wait(timeout=1)
        session.question_count = 1
        return session

    def run_update():
        outcomes["updated"] = store.update("anonymous-session", updater)

    def run_delete():
        delete_started.set()
        outcomes["deleted"] = store.delete("anonymous-session")

    update_thread = Thread(target=run_update)
    delete_thread = Thread(target=run_delete)
    update_thread.start()
    assert update_started.wait(timeout=1)
    delete_thread.start()
    assert delete_started.wait(timeout=1)
    release_update.set()
    update_thread.join(timeout=1)
    delete_thread.join(timeout=1)

    assert update_thread.is_alive() is False
    assert delete_thread.is_alive() is False
    assert outcomes["updated"].question_count == 1
    assert outcomes["deleted"] is True
    assert store.get("anonymous-session") is None


@pytest.mark.parametrize("forbidden_field", ["message", "symptom_text"])
def test_anonymous_event_rejects_raw_health_text_fields(forbidden_field):
    values = {
        "event_name": "session_created",
        "anonymous_session_id": "opaque-id",
        forbidden_field: "头痛两天",
    }

    with pytest.raises(ValidationError):
        AnonymousEvent.model_validate(values)


def test_api_analytics_events_contain_no_raw_message_or_symptom_fields():
    raw_message = "发热三天伴咳嗽"
    before = len(app.state.analytics.events)

    response = client.post("/api/sessions", json={"message": raw_message})

    assert response.status_code == 201
    events = app.state.analytics.events[before:]
    assert events
    for event in events:
        dumped = event.model_dump(mode="json")
        assert set(dumped) <= {
            "event_name",
            "anonymous_session_id",
            "question_id",
            "question_count",
            "urgency_level",
            "feedback_label",
            "feedback_helpful",
            "timestamp",
        }
        assert "message" not in dumped
        assert "symptom_text" not in dumped
        assert raw_message not in str(dumped)


def test_demo_slot_parser_is_offline_fallback_for_incomplete_environment():
    parser = build_slot_parser({"LLM_API_KEY": ""})

    assert isinstance(parser, DemoSlotParser)
    parsed = parser.parse("  头痛两天  ", TriageSlots())
    assert parsed.main_symptom == "头痛两天"
    assert app.state.slot_parser.__class__ is DemoSlotParser


def test_configured_slot_parser_is_used_without_echoing_request_text():
    raw_message = "PRIVATE-OPAQUE-INPUT"
    follow_up = "PRIVATE-FOLLOW-UP"

    class RecordingSlotParser:
        def __init__(self):
            self.messages = []

        def parse(self, text, current):
            self.messages.append(text)
            return current.model_copy(
                update={"main_symptom": "结构化症状", "severity": 8}
            )

    parser = RecordingSlotParser()
    parser_client = TestClient(create_app(slot_parser=parser))

    response = parser_client.post("/api/sessions", json={"message": raw_message})
    continued = parser_client.post(
        f"/api/sessions/{response.json()['session_id']}/messages",
        json={"message": follow_up},
    )

    assert response.status_code == 201
    assert continued.status_code == 200
    assert parser.messages == [raw_message, follow_up]
    assert response.json()["result"]["urgency_level"] == "urgent"
    assert raw_message not in response.text
    assert follow_up not in continued.text
