"""Sprint 22: AI lease document intelligence (US-096).

The Anthropic client is never called for real in tests — `ai_service._client`
is monkeypatched to a fake that returns a canned structured-output response,
shaped exactly like the real SDK response (`.content` blocks, `.stop_reason`).
"""

import json

import pytest

from app.services import ai_service
from tests.conftest import Actor


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.content = [_FakeTextBlock(json.dumps(payload))]
        self.stop_reason = "end_turn"
        self.stop_details = None


class _RefusedResponse:
    def __init__(self) -> None:
        self.content = []
        self.stop_reason = "refusal"

        class _Details:
            explanation = "policy declined"

        self.stop_details = _Details()


class _FakeMessages:
    def __init__(self, response) -> None:
        self._response = response

    async def create(self, **kwargs):
        return self._response


class _FakeClient:
    def __init__(self, response) -> None:
        self.messages = _FakeMessages(response)


ANALYSIS_PAYLOAD = {
    "summary": "The lease is missing a repairs clause and has one vague termination term.",
    "suggestions": [
        {
            "category": "missing_clause",
            "title": "No repairs and maintenance clause",
            "issue": "The lease never states who is responsible for repairs.",
            "suggested_text": "The Landlord shall keep the structure and roof in good repair.",
        },
        {
            "category": "unclear_language",
            "title": "Vague termination notice",
            "issue": "The notice period for termination is not specified.",
            "suggested_text": None,
        },
    ],
}


async def _create_template(owner: Actor) -> dict:
    response = await owner.post(
        "/api/v1/lease-templates",
        json={
            "name": "AI Review Template",
            "body_html": "<p>This lease is between {{ landlord_name }} and {{ tenant_name }}.</p>",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_analyze_creates_suggestions(owner: Actor, monkeypatch: pytest.MonkeyPatch) -> None:
    template = await _create_template(owner)
    monkeypatch.setattr(ai_service, "_client", lambda: _FakeClient(_FakeResponse(ANALYSIS_PAYLOAD)))

    response = await owner.post(f"/api/v1/lease-templates/{template['id']}/analyze")

    assert response.status_code == 200, response.text
    analysis = response.json()
    assert analysis["lease_template_id"] == template["id"]
    assert len(analysis["suggestions"]) == 2
    assert analysis["suggestions"][0]["category"] == "missing_clause"
    assert all(s["status"] == "pending" for s in analysis["suggestions"])


async def test_analyze_without_api_key_returns_503(owner: Actor, monkeypatch: pytest.MonkeyPatch) -> None:
    template = await _create_template(owner)
    from app.core.config import settings

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)

    response = await owner.post(f"/api/v1/lease-templates/{template['id']}/analyze")

    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


async def test_refusal_is_surfaced_as_a_clear_error(owner: Actor, monkeypatch: pytest.MonkeyPatch) -> None:
    template = await _create_template(owner)
    monkeypatch.setattr(ai_service, "_client", lambda: _FakeClient(_RefusedResponse()))

    response = await owner.post(f"/api/v1/lease-templates/{template['id']}/analyze")

    assert response.status_code == 503
    assert "declined" in response.json()["detail"]


async def test_accepting_a_suggestion_appends_the_clause_and_bumps_version(
    owner: Actor, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = await _create_template(owner)
    monkeypatch.setattr(ai_service, "_client", lambda: _FakeClient(_FakeResponse(ANALYSIS_PAYLOAD)))
    analysis = (await owner.post(f"/api/v1/lease-templates/{template['id']}/analyze")).json()
    suggestion = next(s for s in analysis["suggestions"] if s["suggested_text"])

    response = await owner.patch(
        f"/api/v1/lease-templates/suggestions/{suggestion['id']}", json={"status": "accepted"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "accepted"

    templates = await owner.get("/api/v1/lease-templates")
    updated = next(t for t in templates.json() if t["id"] == template["id"])
    assert updated["version"] == template["version"] + 1
    assert "Landlord shall keep the structure" in updated["body_html"]


async def test_dismissing_a_suggestion_leaves_the_template_untouched(
    owner: Actor, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = await _create_template(owner)
    monkeypatch.setattr(ai_service, "_client", lambda: _FakeClient(_FakeResponse(ANALYSIS_PAYLOAD)))
    analysis = (await owner.post(f"/api/v1/lease-templates/{template['id']}/analyze")).json()
    suggestion = analysis["suggestions"][0]

    response = await owner.patch(
        f"/api/v1/lease-templates/suggestions/{suggestion['id']}", json={"status": "dismissed"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"

    templates = await owner.get("/api/v1/lease-templates")
    updated = next(t for t in templates.json() if t["id"] == template["id"])
    assert updated["version"] == template["version"]


async def test_a_suggestion_cannot_be_resolved_twice(owner: Actor, monkeypatch: pytest.MonkeyPatch) -> None:
    template = await _create_template(owner)
    monkeypatch.setattr(ai_service, "_client", lambda: _FakeClient(_FakeResponse(ANALYSIS_PAYLOAD)))
    analysis = (await owner.post(f"/api/v1/lease-templates/{template['id']}/analyze")).json()
    suggestion = analysis["suggestions"][0]

    await owner.patch(f"/api/v1/lease-templates/suggestions/{suggestion['id']}", json={"status": "dismissed"})
    second = await owner.patch(
        f"/api/v1/lease-templates/suggestions/{suggestion['id']}", json={"status": "accepted"}
    )

    assert second.status_code == 400


async def test_cross_tenant_analysis_is_refused(
    owner: Actor, other_owner: Actor, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = await _create_template(owner)
    monkeypatch.setattr(ai_service, "_client", lambda: _FakeClient(_FakeResponse(ANALYSIS_PAYLOAD)))

    response = await other_owner.post(f"/api/v1/lease-templates/{template['id']}/analyze")

    assert response.status_code == 403
