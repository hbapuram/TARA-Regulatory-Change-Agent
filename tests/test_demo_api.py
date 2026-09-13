from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from demo import api

ROOT = Path(__file__).resolve().parent.parent
CLIENT = TestClient(api.app)


def maeve_request() -> api.RunRequest:
    preset = json.loads((ROOT / "demo" / "presets.json").read_text())[0]
    return api.RunRequest(
        holder=preset["holder"],
        holdings=preset["holdings"],
        answers=preset["answers"],
        as_of="2026-09-13",
    )


def test_health_reports_the_complete_loaded_surface():
    health = api.health()
    assert health["ok"] is True
    assert health["pack_count"] == 9
    assert len(health["agents"]) == 9


def test_ai_status_is_explicit_when_no_server_key_is_configured(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    status = api.ai_status()
    assert status["available"] is False
    assert status["mode"] == "deterministic backup only"


def test_ai_demo_route_combines_mcp_orchestration_with_rendered_controls(monkeypatch):
    expected = {
        "summary": "The current 38% rule applies and a reviewer should check the dated actions.",
        "model": "test-model",
        "tool_trace": [
            {"tool": "list_domains", "arguments": {}, "status": "completed"},
            {"tool": "list_holdings", "arguments": {}, "status": "completed"},
        ],
    }
    monkeypatch.setattr(api, "_orchestrate", lambda req: expected)

    result = api.ai_run(maeve_request())

    assert result["orchestration"] == expected
    assert result["run"]["atlas"]["chain_verified"] is True
    assert any(action["obligation_id"] == "OBL-002B" for action in result["run"]["actions"])


def test_mcp_subprocess_context_never_receives_the_openai_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-not-for-mcp")
    env = api._mcp_subprocess_env(tmp_path / "register.json", tmp_path / "atlas.jsonl", tmp_path / "graph.json")
    assert "OPENAI_API_KEY" not in env
    assert env["TARA_REGISTER_JSON"].endswith("register.json")


def test_recommended_preset_is_the_certified_maeve_path():
    presets = api.presets()
    assert presets[0]["id"] == "maeve"
    assert presets[0]["recommended"] is True
    assert presets[0]["focus_obligation_id"] == "OBL-002B"


def test_demo_root_serves_the_browser_interface():
    response = CLIENT.get("/")
    assert response.status_code == 200
    assert "TARA Live Demo" in response.text


def test_maeve_run_selects_38_percent_and_not_41_percent():
    result = api.run(maeve_request())
    actions = {action["obligation_id"]: action for action in result["actions"]}

    assert "OBL-002" not in actions
    assert actions["OBL-002B"]["expected_rate"] == 0.38
    assert actions["OBL-002B"]["suggested_artefact"]["computed_tax"] == 4560.0
    assert result["atlas"]["chain_verified"] is True


def test_maeve_evidence_returns_old_rate_and_closes_current_rate():
    request = maeve_request()
    run = api.run(request)
    action = next(a for a in run["actions"] if a["obligation_id"] == "OBL-002B")

    old = api.verify(api.VerifyRequest(
        **request.model_dump(),
        domain_id="tax",
        action_id=action["action_id"],
        artefact={
            "artefact_type": "tax_computation",
            "rate_applied": 0.41,
            "deemed_gain": 12000.0,
            "computed_tax": 4920.0,
        },
    ))
    current = api.verify(api.VerifyRequest(
        **request.model_dump(),
        domain_id="tax",
        action_id=action["action_id"],
        artefact={
            "artefact_type": "tax_computation",
            "rate_applied": 0.38,
            "deemed_gain": 12000.0,
            "computed_tax": 4560.0,
        },
    ))

    assert old["closure"]["outcome"] == "returned"
    assert current["closure"]["outcome"] == "closed"
    assert current["atlas"]["chain_verified"] is True
