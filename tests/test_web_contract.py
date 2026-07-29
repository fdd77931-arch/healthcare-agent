from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.main import create_app


WEB_ROOT = Path(__file__).parents[1] / "app" / "web"


class LandmarkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.main_count = 0
        self.labels_for: set[str] = set()
        self.ids: set[str] = set()
        self.hidden_ids: set[str] = set()

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        if tag == "main":
            self.main_count += 1
        if tag == "label" and attributes.get("for"):
            self.labels_for.add(attributes["for"])
        if element_id := attributes.get("id"):
            self.ids.add(element_id)
            if "hidden" in attributes:
                self.hidden_ids.add(element_id)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_home_contains_product_boundary_and_accessible_form(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert "循迹" in html
    assert "不提供医学诊断" in html
    assert 'id="symptom-form"' in html
    assert 'aria-live="polite"' in html


def test_home_has_one_main_and_labeled_inputs(client: TestClient):
    parser = LandmarkParser()
    parser.feed(client.get("/").text)

    assert parser.main_count == 1
    assert {"symptom-input", "answer-input"} <= parser.ids
    assert {"symptom-input", "answer-input"} <= parser.labels_for


def test_home_exposes_every_flow_state_and_supporting_control(client: TestClient):
    parser = LandmarkParser()
    parser.feed(client.get("/").text)

    expected_states = {
        "start-state",
        "followup-state",
        "loading-state",
        "emergency-state",
        "result-state",
        "insufficient-state",
        "error-state",
    }
    assert expected_states <= parser.ids
    assert expected_states - {"start-state"} <= parser.hidden_ids
    assert {
        "question-progress",
        "question-rationale",
        "visit-summary",
        "feedback-form",
        "copy-summary",
        "clear-session",
        "retry-request",
        "return-to-edit",
        "emergency-heading",
        "mobile-boundary",
        "feedback-details",
    } <= parser.ids


def test_followup_heading_can_receive_programmatic_focus(client: TestClient):
    html = client.get("/").text

    assert '<h2 id="question-heading" tabindex="-1">' in html


def test_home_has_fixed_emergency_action_and_local_assets(client: TestClient):
    html = client.get("/").text

    assert 'href="tel:120"' in html
    assert "/static/styles.css" in html
    assert "/static/app_logic.js" in html
    assert "/static/app.js" in html
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app_logic.js").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_styles_define_approved_tokens_and_accessibility_guards():
    css = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
    compact = "".join(css.split()).lower()

    for token in (
        "--ink:#173b36",
        "--primary:#176b5d",
        "--surface:#fff",
        "--canvas:#edf5f2",
        "--warning:#9a5b16",
        "--danger:#a23f35",
    ):
        assert token in compact
    assert 'georgia,"songtisc",serif' in compact
    assert "min-block-size:44px" in compact
    assert ":focus-visible" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "@media (min-width:" in css


def test_mobile_first_viewport_prioritizes_form_and_safe_emergency_action(
    client: TestClient,
):
    html = client.get("/").text
    css = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
    compact = "".join(css.split()).lower()

    assert "viewport-fit=cover" in html
    assert 'class="title-mobile"' in html
    assert 'class="orientation-copy-mobile"' in html
    assert "--safe-inline-end:max(12px,env(safe-area-inset-right))" in compact
    assert "--safe-block-start:max(10px,env(safe-area-inset-top))" in compact
    assert "--safe-block-end:max(12px,env(safe-area-inset-bottom))" in compact
    assert "right:var(--safe-inline-end)" in compact
    assert "top:var(--safe-block-start)" in compact
    assert "bottom:auto" in compact
    assert "max-inline-size:calc(100vw-24px)" in compact
    assert ".trail,.boundary-note{display:none;}" in compact
    assert ".start-state{min-block-size:0;padding:20px18px22px;}" in compact
    assert ".title-mobile{display:none;}" in compact
    assert ".trail{display:grid;}" in compact
    assert ".boundary-note{display:grid;}" in compact
    assert ".mobile-boundary{display:flex;}" in compact
    assert "@media(min-width:900px)" in compact
    assert "position:sticky" in compact


def test_risk_states_and_desktop_headline_follow_design_contract():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    css = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
    compact = "".join(css.split()).lower()

    assert html.count('class="headline-line"') == 3
    assert ".headline-line{display:block;white-space:nowrap;}" in compact
    assert ".emergency-state{background:var(--danger-soft);}" in compact
    assert ".insufficient-state{background:var(--warning-soft);}" in compact


def test_client_uses_explicit_api_contract_without_html_injection():
    script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert ".innerHTML" not in script
    assert "textContent" in script
    assert '"/api/sessions"' in script
    assert '"/messages"' in script
    assert '"/api/feedback"' in script
    assert 'method: "DELETE"' in script
    assert "navigator.clipboard" in script
    assert "pendingRequest" in script
    assert ".focus(" in script
