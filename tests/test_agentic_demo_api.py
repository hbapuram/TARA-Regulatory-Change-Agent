from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_demo import api

ROOT = Path(__file__).resolve().parent.parent
CLIENT = TestClient(api.app)


def request_for(preset_id: str) -> api.RunRequest:
    presets = json.loads((ROOT / "agentic_demo" / "presets.json").read_text())
    preset = next(item for item in presets if item["id"] == preset_id)
    return api.RunRequest(
        holder=preset["holder"],
        holdings=preset["holdings"],
        answers=preset.get("answers", {}),
        as_of="2026-09-13",
    )


def test_agentic_demo_serves_a_distinct_browser_shell():
    response = CLIENT.get("/")
    assert response.status_code == 200
    assert "TARA Agentic Demo" in response.text
    assert "Ask the live investigator" in (ROOT / "agentic_demo" / "app.js").read_text()


def test_live_investigator_is_separate_from_authoritative_controls(monkeypatch):
    expected = {
        "summary": "• Section 4.3 changed from 41% to 38%.\n• The controls selected the current rule.\n• A reviewer should check the evidence.",
        "model": "test-model",
        "tool_trace": [
            {"tool": "list_domains", "arguments": {}, "status": "completed"},
            {"tool": "list_holdings", "arguments": {}, "status": "completed"},
            {"tool": "list_sources", "arguments": {"domain_id": "tax"}, "status": "completed"},
            {"tool": "survey_detect_change", "arguments": {"source_id": "revenue-27-01a-02"}, "status": "completed"},
            {"tool": "compass_assess", "arguments": {"holding_id": "HLD-101"}, "status": "completed"},
            {"tool": "course_plan", "arguments": {"holding_id": "HLD-101"}, "status": "completed"},
        ],
    }
    monkeypatch.setattr(api, "_orchestrate_case_investigator", lambda req: expected)

    result = api.agent_investigate(api.AgentInvestigationRequest(**request_for("maeve").model_dump()))

    assert result["investigator"] == expected
    actions = {action["obligation_id"]: action for action in result["controls"]["actions"]}
    assert actions["OBL-002B"]["expected_rate"] == 0.38
    assert actions["OBL-002B"]["suggested_artefact"]["computed_tax"] == 4560.0
    assert result["controls"]["atlas"]["chain_verified"] is True


def test_live_interview_can_explain_only_a_control_selected_question(monkeypatch):
    request = request_for("ciaran")
    controls = api.run(request)
    question = controls["pending_questions"][0]
    expected = {
        "summary": f"{question['text']}\nA qualified reviewer must confirm this before TARA re-runs its deterministic controls.",
        "model": "test-model",
        "tool_trace": [
            {"tool": "list_domains", "arguments": {}, "status": "completed"},
            {"tool": "list_holdings", "arguments": {}, "status": "completed"},
            {"tool": "compass_assess", "arguments": {"holding_id": question["holding_id"]}, "status": "completed"},
        ],
    }
    monkeypatch.setattr(api, "_orchestrate_missing_fact_interview", lambda req, q: expected)

    result = api.agent_interview(api.AgentInterviewRequest(**request.model_dump(), question_id=question["question_id"]))

    assert result["question"] == question
    assert result["interview"] == expected
    assert result["question"]["question_id"] not in request.answers


def test_live_interview_rejects_a_question_that_controls_did_not_request():
    request = request_for("maeve")
    response = CLIENT.post("/api/agent/interview", json={**request.model_dump(), "question_id": "SQ-NOT-PENDING"})

    assert response.status_code == 409
    assert "not currently pending" in response.json()["detail"]


def test_live_interview_summary_preserves_the_question_and_omits_operational_detail():
    question = "Was the property occupied as the holder's only or main residence throughout the entire period of ownership?"
    answer = question + " A qualified reviewer must confirm this fact before the protected checks can continue."

    assert api._safe_interview_summary(answer, question) == question + "\nA qualified reviewer must confirm this fact before the protected checks can continue."


@pytest.mark.parametrize("answer", [
    "Was the property occupied as the holder's only or main residence throughout the entire period of ownership? COMPASS returned EXEMPT.",
    "Was the property occupied as the holder's only or main residence throughout the entire period of ownership? This affects the 38% rate.",
])
def test_live_interview_summary_rejects_decisional_or_numeric_detail(answer):
    question = "Was the property occupied as the holder's only or main residence throughout the entire period of ownership?"

    with pytest.raises(api.HTTPException) as exc:
        api._safe_interview_summary(answer, question)
    assert exc.value.status_code == 502


def test_prepared_case_relay_accepts_only_an_unchanged_checked_in_profile(monkeypatch):
    class Response:
        def read(self):
            return json.dumps({"orchestration": {"summary": "prepared agent output", "model": "relay-model", "tool_trace": []}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setenv("TARA_AGENT_RELAY_URL", "https://relay.invalid")
    monkeypatch.setattr(api, "urlopen", lambda request, timeout: Response())
    prepared = request_for("maeve")

    assert api._relay_orchestration(prepared)["summary"] == "prepared agent output"

    edited = prepared.model_copy(deep=True)
    edited.holder.name = "Not a prepared profile"
    with pytest.raises(api.HTTPException) as exc:
        api._relay_orchestration(edited)
    assert exc.value.status_code == 403


def test_agent_status_labels_prepared_case_relay(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("TARA_AGENT_RELAY_URL", "https://tara-demo.onrender.com")

    status = api.ai_status()
    assert status["available"] is True
    assert status["prepared_case_relay"] is True
